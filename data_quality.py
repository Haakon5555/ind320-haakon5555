"""Generated from the shared function cells in prosjekt_del_3.ipynb."""

from pathlib import Path
import gzip
import hashlib
import json
import time
import tempfile
import fcntl

import numpy as np
import pandas as pd
import requests

WEATHER_URL = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_VARIABLES = ["temperature_2m", "precipitation"]


def _request_weather(params, cache_dir, progress=None):
    """Reuse an unchanged JSON response, or make one quota-limited request."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    request_key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
    response_path = cache_dir / f"{request_key}.json.gz"
    if response_path.exists():
        with gzip.open(response_path, "rt") as source:
            return json.load(source)

    days = (pd.Timestamp(params["end_date"]) - pd.Timestamp(params["start_date"])).days + 1
    locations = len(params["latitude"].split(","))
    cost = locations * max(1, days / 14 * len(WEATHER_VARIABLES) / 10)
    # Leave headroom for interactive requests from the documentation page.
    limits = [(60, 500), (3600, 4500), (86400, 9000)]
    ledger_path = cache_dir / "quota.json"
    last_notice = 0
    for attempt in range(4):
        while True:
            # A file lock keeps notebook and local app requests from sharing a quota unsafely.
            with (cache_dir / "quota.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                now = time.time()
                ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else []
                ledger = [entry for entry in ledger if now - entry[0] < 86400]
                delay = 0
                for window, limit in limits:
                    if window == 3600:
                        # Server hours reset near the UTC hour, with a client seconds offset.
                        # Allow 60 seconds for reset and retain 180 seconds for in-flight calls.
                        hour_start = int((now - 60) // 3600) * 3600
                        used = sum(amount for stamp, amount in ledger if stamp >= hour_start - 180)
                        if used + cost > limit:
                            delay = max(delay, hour_start + 3662 - now)
                        continue
                    entries = [entry for entry in ledger if now - entry[0] < window]
                    used = sum(entry[1] for entry in entries)
                    for stamp, amount in entries:
                        if used + cost <= limit:
                            break
                        delay = max(delay, stamp + window - now + 2)
                        used -= amount
                if delay == 0:
                    ledger.append([now, cost])
                    temporary = ledger_path.with_suffix(".tmp")
                    temporary.write_text(json.dumps(ledger))
                    temporary.replace(ledger_path)
                    break
            if progress and now - last_notice > 55:
                progress(f"API quota pause: about {delay / 60:.0f} minutes remaining.")
                last_notice = now
            time.sleep(min(delay, 30))
        response = None
        try:
            response = requests.get(WEATHER_URL, params=params, timeout=(15, 180))
            if response.status_code == 429:
                raise RuntimeError("Open-Meteo quota reached. Saved batches are safe; resume later.")
            if 500 <= response.status_code < 600:
                response.raise_for_status()
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and payload.get("error"):
                raise ValueError(payload.get("reason", "Open-Meteo returned an error."))
            # Preserve the response body without changing its contents.
            with tempfile.NamedTemporaryFile(dir=cache_dir, suffix=".tmp", delete=False) as target:
                temporary = Path(target.name)
                target.write(gzip.compress(response.content))
            temporary.replace(response_path)
            return payload
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError):
            if attempt == 3 or (response is not None and 400 <= response.status_code < 500):
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("The weather request did not complete.")


def download_weather(region, start_date, end_date, cache_dir="data/weather", progress=None):
    """Fetch ERA5 hourly temperature and precipitation for every point in a region.

    Dates are inclusive and times are UTC. Complete arrays and raw responses are
    cached. A saved batch is reused after an interruption, never replaced by zeros.
    """
    locations_path = Path("data/weather_locations.json")
    coordinates = json.loads(locations_path.read_text())
    if region not in coordinates:
        raise ValueError(f"Unknown region: {region}")
    start, end = pd.Timestamp(start_date), pd.Timestamp(end_date)
    if start.tzinfo is not None or end.tzinfo is not None or start != start.normalize() or end != end.normalize():
        raise ValueError("Use dates without time or timezone, in YYYY-MM-DD format.")
    if end < start or (end - start).days > 366:
        raise ValueError("Select an ordered period of at most 367 days.")
    requested = np.asarray(coordinates[region], dtype=float)
    if requested.shape != (1000, 2) or not np.isfinite(requested).all():
        raise ValueError("Each region must contain 1000 valid longitude/latitude pairs.")
    expected_time = pd.date_range(start, end + pd.Timedelta(days=1), inclusive="left", freq="h", tz="UTC")
    identity = {
        "region": region, "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"), "model": "era5",
        "variables": WEATHER_VARIABLES, "timezone": "GMT",
        "coordinates": requested.tolist(), "cell_selection": "land"
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    array_path = cache_dir / f"{region}_{start:%Y%m%d}_{end:%Y%m%d}_{digest}.npz"
    if array_path.exists():
        with np.load(array_path, allow_pickle=False) as saved:
            result = {key: saved[key] for key in saved.files}
        if not np.array_equal(result["requested_coordinates"], requested):
            raise ValueError("Saved coordinates do not match the request.")
    else:
        temperature = np.empty((1000, len(expected_time)), dtype=np.float32)
        precipitation = np.empty_like(temperature)
        returned = np.empty((1000, 3), dtype=float)
        batch_size = 20
        for offset in range(0, len(requested), batch_size):
            batch = requested[offset:offset + batch_size]
            params = {
                "latitude": ",".join(str(value) for value in batch[:, 1]),
                "longitude": ",".join(str(value) for value in batch[:, 0]),
                "start_date": identity["start_date"], "end_date": identity["end_date"],
                "hourly": ",".join(WEATHER_VARIABLES), "models": "era5", "timezone": "GMT",
                "cell_selection": "land", "temperature_unit": "celsius", "precipitation_unit": "mm"
            }
            payload = _request_weather(params, cache_dir / "raw", progress)
            records = payload if isinstance(payload, list) else [payload]
            if len(records) != len(batch):
                raise ValueError("Open-Meteo returned the wrong number of locations.")
            for position, record in enumerate(records):
                if record.get("location_id", position) != position:
                    raise ValueError("Unexpected location order in the response.")
                hourly = record["hourly"]
                actual_time = pd.DatetimeIndex(pd.to_datetime(hourly["time"], utc=True))
                if not actual_time.equals(expected_time) or record["utc_offset_seconds"] != 0:
                    raise ValueError("Hourly timestamps or timezone do not match the request.")
                units = record["hourly_units"]
                if units["temperature_2m"] != "°C" or units["precipitation"] != "mm":
                    raise ValueError("Unexpected weather units.")
                index = offset + position
                temperature[index] = hourly["temperature_2m"]
                precipitation[index] = hourly["precipitation"]
                returned[index] = [record["longitude"], record["latitude"], record["elevation"]]
            if progress:
                progress(f"{region}: {offset + len(batch)}/1000 locations checked.")
        result = {
            "time_ns": expected_time.asi8, "temperature_2m": temperature,
            "precipitation": precipitation, "requested_coordinates": requested,
            "returned_coordinates_elevation": returned,
        }
        if not np.isfinite(temperature).all() or not np.isfinite(precipitation).all():
            raise ValueError("Weather data contain missing or non-finite values. Inspect the raw responses.")
        if (precipitation < 0).any():
            raise ValueError("Negative precipitation returned by the API.")
        with tempfile.NamedTemporaryFile(dir=cache_dir, suffix=".tmp", delete=False) as target:
            temporary = Path(target.name)
            np.savez_compressed(target, **result)
        temporary.replace(array_path)
    for variable in WEATHER_VARIABLES:
        if result[variable].shape != (1000, len(expected_time)) or not np.isfinite(result[variable]).all():
            raise ValueError(f"Incomplete saved data for {variable}.")
    if not np.array_equal(result["time_ns"], expected_time.asi8):
        raise ValueError("Saved time axis does not match the period.")
    return result


def weather_mean(weather):
    """Equal-area Monte Carlo mean across all 1000 sampled points, for each hour."""
    return pd.DataFrame({
        variable: weather[variable].mean(axis=0, dtype=np.float64)
        for variable in WEATHER_VARIABLES
    }, index=pd.DatetimeIndex(pd.to_datetime(weather["time_ns"], utc=True), name="time"))


def weather_summary_file(region, year, cache_dir="data/weather"):
    """Identify a summary by area, year, model and the exact sampled coordinates."""
    coordinates = json.loads(Path("data/weather_locations.json").read_text())[region]
    sample_hash = hashlib.sha256(json.dumps(coordinates).encode()).hexdigest()[:12]
    return Path(cache_dir) / f"{region}_{year}_era5_{sample_hash}_hourly.csv.gz"


import matplotlib.dates as mdates
from matplotlib.figure import Figure
from scipy.fft import dct, idct
from scipy.signal import stft
from scipy.stats import median_abs_deviation
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler
from statsmodels.tsa.seasonal import STL


def _regular_series(series, step, minimum):
    """Reject gaps and non-finite inputs rather than silently changing the data."""
    series = series.astype(float).sort_index()
    if not isinstance(series.index, pd.DatetimeIndex) or series.index.has_duplicates:
        raise ValueError("Use a unique DatetimeIndex.")
    if len(series) < minimum or not np.isfinite(series.to_numpy()).all():
        raise ValueError(f"At least {minimum} finite observations are required.")
    if not np.all(np.diff(series.index.asi8) == pd.Timedelta(step).value):
        raise ValueError(f"Observations must be regularly spaced by {step}, without gaps.")
    return series


def _date_axis(axis):
    locator = mdates.AutoDateLocator(minticks=4, maxticks=8)
    axis.xaxis.set_major_locator(locator)
    axis.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    axis.grid(alpha=0.2)


def precipitation_spc(series, cutoff_days=30.0, deviations=3.0, title="NO3 precipitation"):
    """DCT high-pass residuals define robust limits on the original rainfall scale."""
    series = _regular_series(series, "1h", 48)
    if cutoff_days <= 2 / 24 or deviations <= 0:
        raise ValueError("The cutoff must exceed two hours and deviations must be positive.")
    values = series.to_numpy()
    # DCT-I frequencies are k / (2 * (N - 1) * dt), with dt = one hour.
    coefficients = dct(values, type=1, norm="forward")
    frequencies = np.arange(len(values)) / (2 * (len(values) - 1))
    high_pass = coefficients.copy()
    high_pass[frequencies < 1 / (24 * cutoff_days)] = 0
    residual = idct(high_pass, type=1, norm="forward")
    # Suppress floating-point noise for constant signals.
    tolerance = 100 * np.finfo(float).eps * max(1, np.max(np.abs(values)))
    residual[np.abs(residual) < tolerance] = 0
    baseline = values - residual
    center = np.median(residual)
    robust_sigma = median_abs_deviation(residual, scale="normal")
    lower = baseline + center - deviations * robust_sigma
    upper = baseline + center + deviations * robust_sigma
    mask = (values < lower) | (values > upper)
    result = pd.DataFrame({"precipitation": values, "lower_limit": lower,
                           "upper_limit": upper, "outlier": mask}, index=series.index)
    summary = {
        "hours": len(values), "outlier_hours": int(mask.sum()),
        "outlier_percent": 100 * mask.mean(), "robust_sigma_mm": robust_sigma,
        "cutoff_days": cutoff_days, "deviations": deviations,
        "maximum_hourly_precipitation_mm": values.max(),
    }
    fig = Figure(figsize=(11, 4))
    ax = fig.subplots()
    ax.plot(series.index, values, color="#397FA3", linewidth=0.6, label="Mean precipitation")
    ax.plot(series.index, lower, color="#BA771E", linewidth=0.8, linestyle="--", label="SPC limits")
    ax.plot(series.index, upper, color="#BA771E", linewidth=0.8, linestyle="--")
    ax.scatter(series.index[mask], values[mask], color="#C33C54", s=7, label="Flagged hours", zorder=3)
    ax.set(title=title, ylabel="Precipitation (mm per preceding hour)", xlabel="Time (UTC)")
    ax.legend(fontsize=8, ncol=3)
    _date_axis(ax)
    fig.tight_layout()
    return fig, summary, result



def temperature_lof(series, contamination=0.01, neighbors=20, title="NO3 temperature"):
    """Flag unusual combinations of temperature and one-hour temperature change."""
    series = _regular_series(series, "1h", 48)
    if not 0 < contamination <= 0.5 or not 2 <= neighbors < len(series) - 1:
        raise ValueError("Use contamination in (0, 0.5] and a valid neighbour count.")
    features = pd.DataFrame({"temperature": series, "hourly_change": series.diff()}).iloc[1:]
    scaled = StandardScaler().fit_transform(features)
    model = LocalOutlierFactor(n_neighbors=neighbors, contamination=contamination)
    labels = model.fit_predict(scaled)
    result = pd.DataFrame({"temperature": series, "lof_score": np.nan, "anomaly": False})
    result.loc[features.index, "lof_score"] = -model.negative_outlier_factor_
    result.loc[features.index, "anomaly"] = labels == -1
    mask = result["anomaly"]
    summary = {
        "scored_hours": len(features), "anomaly_hours": int(mask.sum()),
        "anomaly_percent": 100 * mask.sum() / len(features),
        "contamination": contamination, "neighbors": neighbors,
        "score_threshold": -model.offset_,
    }
    fig = Figure(figsize=(11, 4))
    ax = fig.subplots()
    ax.plot(series.index, series, color="#397FA3", linewidth=0.6, label="Mean temperature")
    ax.scatter(series.index[mask], series[mask], color="#C33C54", s=12, label="LOF anomalies", zorder=3)
    ax.set(title=title, ylabel="Temperature (°C)", xlabel="Time (UTC)")
    ax.legend(fontsize=8)
    _date_axis(ax)
    fig.tight_layout()
    return fig, summary, result



def reservoir_stl(series, seasonal=7, trend=105, robust=True, title="NO3 reservoir filling"):
    """Decompose regularly spaced weekly filling percentages with a 52-week period."""
    series = _regular_series(series, "7d", 104)
    if seasonal < 7 or seasonal % 2 != 1 or trend <= 52 or trend % 2 != 1:
        raise ValueError("Seasonal must be odd and at least 7; trend must be odd and greater than 52.")
    fitted = STL(series, period=52, seasonal=seasonal, trend=trend, robust=robust).fit()
    components = pd.DataFrame({"observed": series, "trend": fitted.trend,
                               "seasonal": fitted.seasonal, "residual": fitted.resid})
    fig = Figure(figsize=(11, 8))
    axes = fig.subplots(4, 1, sharex=True)
    for ax, column in zip(axes, components.columns):
        ax.plot(components.index, components[column], linewidth=0.9, color="#397FA3")
        ax.set_ylabel("Filling (%)" if column == "observed" else
                      "Trend (%)" if column == "trend" else f"{column.capitalize()} (pp)")
        _date_axis(ax)
    axes[0].set_title(title)
    axes[-1].set_xlabel("Measurement date")
    fig.tight_layout()
    return fig, components



def reservoir_spectrogram(series, window=104, overlap=78, title="NO3 filling spectrogram"):
    """STFT of the same weekly series, using complete windows without zero padding."""
    series = _regular_series(series, "7d", 104)
    if not 8 <= window <= len(series) or not 0 <= overlap < window:
        raise ValueError("Window must be between 8 and the series length; overlap must be smaller.")
    samples_per_year = 365.2425 / 7
    frequencies, times, spectrum = stft(
        series.to_numpy(), fs=samples_per_year, window="hann", nperseg=window,
        noverlap=overlap, detrend="constant", boundary=None, padded=False
    )
    dates = series.index[0] + pd.to_timedelta(times * 365.2425, unit="D")
    magnitude = np.abs(spectrum)
    fig = Figure(figsize=(11, 6))
    axes = fig.subplots(2, 1, sharex=True)
    axes[0].plot(series.index, series, color="#397FA3", linewidth=0.9)
    axes[0].set(ylabel="Filling (%)", title=title)
    _date_axis(axes[0])
    mesh = axes[1].pcolormesh(mdates.date2num(dates), frequencies, magnitude, shading="auto", cmap="magma")
    axes[1].set(ylabel="Frequency (cycles/year)", xlabel="Window centre date", ylim=(0, 4))
    axes[1].axhline(1, color="white", linestyle="--", linewidth=0.7)
    _date_axis(axes[1])
    fig.colorbar(mesh, ax=axes, label="STFT magnitude (pp)", fraction=0.03, pad=0.02)
    fig.subplots_adjust(left=0.09, right=0.85, bottom=0.1, top=0.94, hspace=0.18)
    summary = {"window_weeks": window, "overlap_weeks": overlap,
               "frequency_resolution_cycles_per_year": samples_per_year / window,
               "windows": len(times),
               "dominant_nonzero_frequency": frequencies[1:][np.argmax(magnitude[1:].mean(axis=1))]}
    return fig, summary
