"""Generated from the shared function cells in prosjekt_del_3.ipynb."""

from pathlib import Path
import gzip
import hashlib
import json
import time

import numpy as np
import pandas as pd
import requests

WEATHER_URL = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_VARIABLES = ["temperature_2m", "precipitation"]


def _request_weather(params, cache_dir):
    """Reuse a saved JSON response, or request one batch from Open-Meteo."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    # The request parameters identify which saved response can be reused.
    request_key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
    response_path = cache_dir / f"{request_key}.json.gz"
    if response_path.exists():
        with gzip.open(response_path, "rt") as source:
            return json.load(source)

    # Status 429 means the quota is used up. The minute limit clears quickly,
    # so wait and try again a few times before giving up.
    for attempt in range(4):
        response = requests.get(WEATHER_URL, params=params, timeout=(15, 180))
        if response.status_code != 429:
            break
        time.sleep(60)
    if response.status_code == 429:
        raise RuntimeError("Open-Meteo quota reached. Saved batches are kept, so continue later.")
    response.raise_for_status()
    # Save the response body unchanged, so an interrupted download can resume.
    response_path.write_bytes(gzip.compress(response.content))
    return response.json()


def weather_cache_file(region, start_date, end_date, cache_dir="data/weather"):
    """Path of the NPZ file with complete data for one region and period."""
    start, end = pd.Timestamp(start_date), pd.Timestamp(end_date)
    return Path(cache_dir) / f"{region}_{start:%Y%m%d}_{end:%Y%m%d}.npz"


def download_weather(region, start_date, end_date, cache_dir="data/weather", progress=None):
    """Fetch ERA5 hourly temperature and precipitation for every point in a region.

    Dates are inclusive and times are UTC. Returns a dictionary with the time axis,
    both weather arrays (locations x hours) and the requested and returned coordinates.
    Complete arrays and raw responses are saved and reused.
    """
    coordinates = json.loads(Path("data/weather_locations.json").read_text())
    if region not in coordinates:
        raise ValueError(f"Unknown region: {region}")
    requested = np.asarray(coordinates[region], dtype=float)
    start, end = pd.Timestamp(start_date), pd.Timestamp(end_date)
    # Include all hours of the final day, without including midnight of the next day.
    expected_time = pd.date_range(start, end + pd.Timedelta(days=1), inclusive="left", freq="h", tz="UTC")
    array_path = weather_cache_file(region, start, end, cache_dir)
    saved_before = array_path.exists()
    # Prefer complete saved arrays. Otherwise build them from batches of 20 locations.
    if saved_before:
        with np.load(array_path) as saved:
            result = {key: saved[key] for key in saved.files}
        if not np.array_equal(result["requested_coordinates"], requested):
            raise ValueError("Saved coordinates do not match the request.")
    else:
        # Rows are locations and columns are hours. Returned grid metadata are kept separately.
        temperature = np.empty((len(requested), len(expected_time)), dtype=np.float32)
        precipitation = np.empty_like(temperature)
        returned = np.empty((len(requested), 3), dtype=float)
        batch_size = 20
        for offset in range(0, len(requested), batch_size):
            batch = requested[offset:offset + batch_size]
            # Stored pairs are longitude/latitude. The API expects separate named lists.
            params = {
                "latitude": ",".join(str(value) for value in batch[:, 1]),
                "longitude": ",".join(str(value) for value in batch[:, 0]),
                "start_date": start.strftime("%Y-%m-%d"), "end_date": end.strftime("%Y-%m-%d"),
                "hourly": ",".join(WEATHER_VARIABLES), "models": "era5", "timezone": "GMT",
                "cell_selection": "land", "temperature_unit": "celsius", "precipitation_unit": "mm"
            }
            records = _request_weather(params, Path(cache_dir) / "raw")
            # Check each location before placing its observations in the full arrays.
            for index, record in enumerate(records, start=offset):
                hourly = record["hourly"]
                if not pd.to_datetime(hourly["time"], utc=True).equals(expected_time):
                    raise ValueError("Hourly timestamps do not match the request.")
                units = record["hourly_units"]
                if units["temperature_2m"] != "°C" or units["precipitation"] != "mm":
                    raise ValueError("Unexpected weather units.")
                temperature[index] = hourly["temperature_2m"]
                precipitation[index] = hourly["precipitation"]
                returned[index] = [record["longitude"], record["latitude"], record["elevation"]]
            if progress:
                progress(f"{region}: {offset + len(batch)}/{len(requested)} locations checked.")
        result = {
            "time_ns": expected_time.asi8, "temperature_2m": temperature,
            "precipitation": precipitation, "requested_coordinates": requested,
            "returned_coordinates_elevation": returned,
        }
    # Apply the same shape, missing-value and time checks to loaded and downloaded data.
    for variable in WEATHER_VARIABLES:
        if result[variable].shape != (len(requested), len(expected_time)) or not np.isfinite(result[variable]).all():
            raise ValueError(f"Incomplete data for {variable}.")
    if not np.array_equal(result["time_ns"], expected_time.asi8):
        raise ValueError("Time axis does not match the period.")
    # Save the NPZ only after all locations have passed the checks.
    if not saved_before:
        np.savez_compressed(array_path, **result)
    return result


def weather_mean(weather):
    """Equal-area Monte Carlo mean across all 1000 sampled points, for each hour."""
    # axis=0 averages locations, leaving one value per hour. Use float64 for the mean.
    return pd.DataFrame({
        variable: weather[variable].mean(axis=0, dtype=np.float64)
        for variable in WEATHER_VARIABLES
    }, index=pd.DatetimeIndex(pd.to_datetime(weather["time_ns"], utc=True), name="time"))


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
    # Sort without filling gaps or combining duplicate timestamps.
    series = series.astype(float).sort_index()
    if not isinstance(series.index, pd.DatetimeIndex) or series.index.has_duplicates:
        raise ValueError("Use a unique DatetimeIndex.")
    if len(series) < minimum or not np.isfinite(series.to_numpy()).all():
        raise ValueError(f"At least {minimum} finite observations are required.")
    # Compare adjacent timestamps in nanoseconds with the required time step.
    if not np.all(np.diff(series.index.asi8) == pd.Timedelta(step).value):
        raise ValueError(f"Observations must be regularly spaced by {step}, without gaps.")
    return series


def _date_axis(axis):
    # Choose a small number of date labels that adapt to the displayed period.
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
    # Convert the cutoff from days to cycles/hour and remove slower components.
    high_pass[frequencies < 1 / (24 * cutoff_days)] = 0
    residual = idct(high_pass, type=1, norm="forward")
    # Add robust residual limits back to the smooth baseline, in the original units.
    baseline = values - residual
    center = np.median(residual)
    robust_sigma = median_abs_deviation(residual, scale="normal")
    lower = baseline + center - deviations * robust_sigma
    upper = baseline + center + deviations * robust_sigma
    # Keep every observation. The Boolean mask only marks values outside the limits.
    mask = (values < lower) | (values > upper)
    result = pd.DataFrame({"precipitation": values, "lower_limit": lower,
                           "upper_limit": upper, "outlier": mask}, index=series.index)
    summary = {
        "hours": len(values), "outlier_hours": int(mask.sum()),
        "outlier_percent": 100 * mask.mean(), "robust_sigma_mm": robust_sigma,
        "cutoff_days": cutoff_days, "deviations": deviations,
        "maximum_hourly_precipitation_mm": values.max(),
    }
    # Plot the original rainfall, limits and flags, without plotting the residual.
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
    # Pair each temperature with its hourly change. The first hour has no pair.
    features = pd.DataFrame({"temperature": series, "hourly_change": series.diff()}).iloc[1:]
    # Put both features on comparable scales before measuring neighbour distances.
    scaled = StandardScaler().fit_transform(features)
    model = LocalOutlierFactor(n_neighbors=neighbors, contamination=contamination)
    labels = model.fit_predict(scaled)
    # Retain the full time axis, including the unscored first hour.
    result = pd.DataFrame({"temperature": series, "lof_score": np.nan, "anomaly": False})
    # Reverse sklearn’s score sign so higher scores mean more unusual combinations.
    result.loc[features.index, "lof_score"] = -model.negative_outlier_factor_
    result.loc[features.index, "anomaly"] = labels == -1
    mask = result["anomaly"]
    summary = {
        "scored_hours": len(features), "anomaly_hours": int(mask.sum()),
        "anomaly_percent": 100 * mask.sum() / len(features),
        "contamination": contamination, "neighbors": neighbors,
        "score_threshold": -model.offset_,
    }
    # Show flags on the original temperature curve, not on the standardised features.
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
    # Estimate the three additive components using a 52-observation annual cycle.
    fitted = STL(series, period=52, seasonal=seasonal, trend=trend, robust=robust).fit()
    # Keep all components aligned with the input dates for plotting and reconstruction.
    components = pd.DataFrame({"observed": series, "trend": fitted.trend,
                               "seasonal": fitted.seasonal, "residual": fitted.resid})
    fig = Figure(figsize=(11, 8))
    axes = fig.subplots(4, 1, sharex=True)
    # Levels use percent. Seasonal and residual deviations use percentage points.
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
    # Weekly sampling expressed per year makes the frequency axis cycles/year.
    samples_per_year = 365.2425 / 7
    # Remove each window’s mean and use only complete windows, without zero padding.
    frequencies, times, spectrum = stft(
        series.to_numpy(), fs=samples_per_year, window="hann", nperseg=window,
        noverlap=overlap, detrend="constant", boundary=None, padded=False
    )
    # STFT times are in years with this sampling rate. Convert them to calendar dates.
    dates = series.index[0] + pd.to_timedelta(times * 365.2425, unit="D")
    # Plot coefficient magnitudes rather than complex values or squared power.
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
    # Ignore zero frequency when finding the strongest average oscillation.
    summary = {"window_weeks": window, "overlap_weeks": overlap,
               "frequency_resolution_cycles_per_year": samples_per_year / window,
               "windows": len(times),
               "dominant_nonzero_frequency": frequencies[1:][np.argmax(magnitude[1:].mean(axis=1))]}
    return fig, summary
