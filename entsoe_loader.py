"""Read ENTSO-E physical flows (A11) using the existing requests/pandas packages."""

from pathlib import Path
import math
import time
import xml.etree.ElementTree as ET

import pandas as pd
import requests


# ENTSO-E's area catalogue, also linked from notebook section 2.
AREA_CODES = {
    "NO1": "10YNO-1--------2", "NO2": "10YNO-2--------T",
    "NO3": "10YNO-3--------J", "NO4": "10YNO-4--------9",
    "SE1": "10Y1001A1001A44P", "SE2": "10Y1001A1001A45N",
    "SE3": "10Y1001A1001A46L", "DE-LU": "10Y1001A1001A82H",
    "DK1": "10YDK-1--------W", "GB": "10YGB----------A",
    "NL": "10YNL----------L", "FI": "10YFI-1--------U",
}
CONNECTIONS = (
    ("NO1", "SE3"), ("NO2", "DE-LU"), ("NO2", "DK1"), ("NO2", "GB"),
    ("NO2", "NL"), ("NO3", "SE2"), ("NO4", "FI"), ("NO4", "SE1"),
    ("NO4", "SE2"),
)
API_URL = "https://web-api.tp.entsoe.eu/api"


def parse_physical_flows(xml, out_area, in_area, start, end):
    """Validate one directional response and return complete hourly mean MW."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        raise ValueError("ENTSO-E returned invalid XML.") from None
    # Remove namespaces so the same code handles supported document versions.
    for element in root.iter():
        element.tag = element.tag.rsplit("}", 1)[-1]
    if root.tag == "Acknowledgement_MarketDocument":
        raise ValueError("ENTSO-E returned an acknowledgement without usable data.")
    if root.findtext("type") != "A11":
        raise ValueError("Expected an ENTSO-E physical-flow document (A11).")

    rows = []
    for series in root.findall("TimeSeries"):
        if (series.findtext("out_Domain.mRID") != AREA_CODES[out_area]
                or series.findtext("in_Domain.mRID") != AREA_CODES[in_area]):
            raise ValueError("Unexpected area or direction in ENTSO-E response.")
        if series.findtext("quantity_Measure_Unit.name") != "MAW":
            raise ValueError("Expected power measured in MW.")
        curve = series.findtext("curveType", "A01")
        if curve not in ("A01", "A03"):
            raise ValueError("Unsupported ENTSO-E curve type.")
        for period in series.findall("Period"):
            begin = pd.Timestamp(period.findtext("timeInterval/start"))
            finish = pd.Timestamp(period.findtext("timeInterval/end"))
            step = pd.Timedelta(period.findtext("resolution"))
            if begin.tzinfo is None or finish.tzinfo is None:
                raise ValueError("ENTSO-E timestamps must include a timezone.")
            if step not in [pd.Timedelta(minutes=m) for m in (15, 30, 60)]:
                raise ValueError("Expected 15, 30 or 60 minute physical-flow intervals.")
            if finish <= begin or (finish - begin) % step:
                raise ValueError("Invalid ENTSO-E period boundaries.")
            count = int((finish - begin) / step)
            points = []
            for point in period.findall("Point"):
                position = int(point.findtext("position"))
                # Missing publications must not become zero or forward-filled values.
                quantity = point.findtext("quantity")
                if quantity is None:
                    raise ValueError("Missing ENTSO-E quantity.")
                value = float(quantity)
                if not math.isfinite(value) or value < 0 or not 1 <= position <= count:
                    raise ValueError("Invalid ENTSO-E position or power value.")
                points.append((position, value))
            points.sort()
            positions = [position for position, value in points]
            if not positions or positions[0] != 1 or len(set(positions)) != len(positions):
                raise ValueError("Missing first position or duplicate ENTSO-E positions.")
            if curve == "A01" and positions != list(range(1, count + 1)):
                raise ValueError("Missing fixed-size ENTSO-E intervals.")
            for index, (position, value) in enumerate(points):
                # A03 values remain constant until the next change or period end.
                stop = (points[index + 1][0] if index + 1 < len(points) else count + 1)
                if curve == "A01":
                    stop = position + 1
                for slot in range(position, stop):
                    timestamp = begin + (slot - 1) * step
                    if start <= timestamp < end:
                        rows.append((timestamp, timestamp + step, value))
    if not rows:
        raise ValueError("No ENTSO-E physical flows were returned.")

    data = pd.DataFrame(rows, columns=["start_utc", "end_utc", "power_mw"])
    data = data.sort_values("start_utc").reset_index(drop=True)
    # Exact continuity detects gaps, overlaps and duplicate time series.
    if (data["start_utc"].iloc[0] != start or data["end_utc"].iloc[-1] != end
            or not data["start_utc"].iloc[1:].reset_index(drop=True).equals(
                data["end_utc"].iloc[:-1].reset_index(drop=True))):
        raise ValueError("ENTSO-E intervals have gaps, overlaps or incomplete coverage.")
    data["hours"] = (data["end_utc"] - data["start_utc"]).dt.total_seconds() / 3600
    data["hour"] = data["start_utc"].dt.floor("h")
    if (data["end_utc"] > data["hour"] + pd.Timedelta(hours=1)).any():
        raise ValueError("ENTSO-E intervals cross an hourly aggregation boundary.")
    data["energy_mwh"] = data["power_mw"] * data["hours"]
    hourly = data.groupby("hour").agg(hours=("hours", "sum"), energy=("energy_mwh", "sum"))
    expected = pd.date_range(start, end, freq="h", inclusive="left")
    if not hourly.index.equals(expected) or not hourly["hours"].eq(1).all():
        raise ValueError("Incomplete hourly ENTSO-E coverage.")
    # One-hour average MW equals that hour's energy in MWh.
    result = hourly["energy"].rename("power_mw").rename_axis("start_utc").reset_index()
    result["end_utc"] = result["start_utc"] + pd.Timedelta(hours=1)
    return result


def _download(session, token, out_area, in_area, start, end):
    params = {
        "documentType": "A11", "out_Domain": AREA_CODES[out_area],
        "in_Domain": AREA_CODES[in_area],
        "periodStart": start.strftime("%Y%m%d%H%M"),
        "periodEnd": end.strftime("%Y%m%d%H%M"), "securityToken": token,
    }
    for attempt in range(3):
        try:
            response = session.get(API_URL, params=params, timeout=(15, 120))
        except requests.RequestException:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            # Raw request exceptions may include the token in the URL.
            raise RuntimeError("ENTSO-E connection failed. Check internet access and retry.") from None
        if response.status_code in (401, 403):
            raise RuntimeError("ENTSO-E rejected the token. Check the token and API activation.")
        if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
            time.sleep(10 * (attempt + 1))
            continue
        if response.status_code != 200:
            raise RuntimeError(f"ENTSO-E request failed (HTTP {response.status_code}).")
        return response.content


def load_api_flows(token, source_dir=Path("data/entsoe"), years=(2024, 2025)):
    """Fetch both directions, preserve XML sources, and reuse them on later runs."""
    if not token or not token.strip():
        raise ValueError("Set ENTSOE_API_TOKEN in .streamlit/secrets.toml.")
    source_dir = Path(source_dir)
    frames = []
    with requests.Session() as session:
        for norway, foreign in CONNECTIONS:
            for year in years:
                start = pd.Timestamp(f"{year}-01-01", tz="UTC")
                end = pd.Timestamp(f"{year + 1}-01-01", tz="UTC")
                for direction, out_area, in_area in (
                    ("Export", norway, foreign), ("Import", foreign, norway)
                ):
                    filename = f"api_{out_area.lower()}_{in_area.lower()}_{year}.xml"
                    path = source_dir / filename
                    cached = path.is_file()
                    xml = path.read_bytes() if cached else _download(
                        session, token.strip(), out_area, in_area, start, end
                    )
                    try:
                        frame = parse_physical_flows(xml, out_area, in_area, start, end)
                    except (ValueError, TypeError, OverflowError):
                        raise ValueError(
                            f"Invalid or incomplete ENTSO-E data: {out_area} to {in_area}, "
                            f"{year}. No CSV fallback or database update was performed."
                        ) from None
                    if not cached:
                        # Preserve the response, never the authenticated request URL.
                        source_dir.mkdir(parents=True, exist_ok=True)
                        with path.open("xb") as handle:
                            handle.write(xml)
                    frame["source_file"] = filename
                    frame["out_area"], frame["in_area"] = out_area, in_area
                    frame["norway_area"], frame["foreign_area"] = norway, foreign
                    frame["connection"] = f"{norway} / {foreign}"
                    frame["direction"], frame["year"] = direction, year
                    frame["duration_hours"] = 1.0
                    frames.append(frame)
                    print(f"{out_area} to {in_area}, {year}: {len(frame):,} hours "
                          f"({'saved API response' if cached else 'API download'}).")
    return pd.concat(frames, ignore_index=True)
