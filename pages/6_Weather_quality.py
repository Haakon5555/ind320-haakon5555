"""Download regional ERA5 data and inspect precipitation SPC and temperature LOF."""
import matplotlib.dates as mdates
import pandas as pd
import requests
import streamlit as st

from data_loader import select_data, select_analysis_area
from data_quality import download_weather, weather_mean, weather_cache_file, precipitation_spc, temperature_lof

st.set_page_config(page_title="IND320 - Weather quality", layout="wide")
st.title("Weather data quality")
st.session_state.setdefault("chosen_area_type", "EL")
st.session_state.setdefault("chosen_months", ("2024-01", "2024-12"))
if st.button("Use NO3, 2024"):
    st.session_state["chosen_area_type"] = "EL"
    st.session_state["area_type_control"] = "EL"
    st.session_state["chosen_area"] = ("EL", 3)
    st.session_state["analysis_area_EL"] = 3
    st.session_state["chosen_months"] = ("2024-01", "2024-12")
    st.session_state.pop("period_control", None)
selected, area_type, start, end = select_data()
area, number, region = select_analysis_area(selected, area_type)
if region is None:
    st.info("Select an EL or VASS area. No separate weather sample was drawn for the Norway total.")
    st.stop()
if start.year != end.year:
    st.info("Choose months within one calendar year. Weather thresholds are estimated from that complete year.")
    st.stop()
year = start.year
if pd.Timestamp(f"{year}-12-31") > pd.Timestamp.now().normalize() - pd.Timedelta(days=6):
    st.info("Select a completed calendar year so the full-year ERA5 analysis is available.")
    st.stop()
if area_type == "VASS":
    st.caption(
        "Weather uses the three region groups specified in the course. These administrative polygons "
        "are approximations, not individual reservoir catchments or the four groups in NVE's current catalogue."
    )
start_date, end_date = f"{year}-01-01", f"{year}-12-31"
cache_path = weather_cache_file(region, start_date, end_date)
st.write(f"{region}, {year}: hourly ERA5 temperature and precipitation averaged over 1000 sampled locations.")
st.caption("SPC limits and LOF are fitted to the full year. The charts and event tables show the months selected in the sidebar.")
if not cache_path.exists():
    st.info("These weather data have not been prepared yet. A full-year download can use up the hourly API quota. If it stops, press the button again later. Completed batches are reused.")
    if not st.button(f"Download {year} weather for {region}", type="primary"):
        st.stop()
    progress = st.empty()
    try:
        with st.spinner("Retrieving weather data…"):
            download_weather(region, start_date, end_date, progress=progress.info)
        progress.success("All 1000 locations are complete.")
    except (requests.RequestException, ValueError, RuntimeError, OSError) as error:
        st.error(f"Weather download stopped: {error}")
        st.stop()

@st.cache_data(max_entries=8)
def read_hourly(region, year, path, modified):
    # Cache only the small hourly table. The NPZ path and timestamp detect changes.
    weather = download_weather(region, f"{year}-01-01", f"{year}-12-31")
    return weather_mean(weather)

try:
    hourly = read_hourly(region, year, str(cache_path), cache_path.stat().st_mtime_ns)
except (requests.RequestException, ValueError, RuntimeError, OSError) as error:
    st.error(f"Could not read the saved weather data: {error}")
    st.stop()
expected = pd.date_range(f"{year}-01-01", f"{year+1}-01-01", inclusive="left", freq="h", tz="UTC")
if not hourly.index.equals(expected) or hourly.isna().any().any():
    st.error("The saved weather data are incomplete. Check the NPZ file and its source responses.")
    st.stop()
view_start, view_end = start.tz_localize("UTC"), end.tz_localize("UTC")
spc_tab, lof_tab = st.tabs(["Precipitation / SPC", "Temperature / LOF"])
with spc_tab:
    a, b = st.columns(2)
    cutoff = a.number_input("DCT cutoff period (days)", min_value=0.25, max_value=366.0, value=30.0, step=1.0)
    deviations = b.number_input("Robust standard deviations", min_value=0.1, max_value=10.0, value=3.0, step=0.5)
    figure, summary, result = precipitation_spc(hourly["precipitation"], cutoff, deviations, f"{region}, {year}: precipitation")
    figure.axes[0].set_xlim(mdates.date2num(view_start), mdates.date2num(view_end))
    st.pyplot(figure)
    visible = result.loc[view_start:view_end]
    a, b, c = st.columns(3)
    a.metric("Flagged hours in view", f"{visible.outlier.sum():,}")
    b.metric("Flagged hours in full year", f"{summary['outlier_hours']:,}")
    c.metric("Full-year robust sigma", f"{summary['robust_sigma_mm']:.3f} mm")
    st.caption("Limits use the median and scaled MAD of the DCT high-pass residual. Flags identify unusual values, not proven errors. Rainfall is skewed, so 3 sigma has no fixed false-alarm probability here.")
    st.dataframe(visible.loc[visible.outlier], width="stretch")
with lof_tab:
    a, b = st.columns(2)
    proportion = a.slider("Outlier proportion (%)", min_value=0.1, max_value=10.0, value=1.0, step=0.1)
    neighbors = b.number_input("Neighbours", min_value=2, max_value=200, value=20, step=1)
    figure, summary, result = temperature_lof(hourly["temperature_2m"], proportion / 100, int(neighbors), f"{region}, {year}: temperature")
    figure.axes[0].set_xlim(mdates.date2num(view_start), mdates.date2num(view_end))
    st.pyplot(figure)
    visible = result.loc[view_start:view_end]
    a, b = st.columns(2)
    a.metric("Anomalies in view", f"{visible.anomaly.sum():,}")
    b.metric("Anomalies in full year", f"{summary['anomaly_hours']:,}")
    st.caption("LOF compares standardised temperature and one-hour temperature change. The first hour is not scored. The chosen proportion controls the threshold and is not an estimated error rate.")
    st.dataframe(visible.loc[visible.anomaly].sort_values("lof_score", ascending=False), width="stretch")
st.markdown("Weather: [Open-Meteo](https://open-meteo.com/en/docs/historical-weather-api), ERA5 / Copernicus Climate Change Service. Hourly timestamps use UTC. No flagged observations are removed.")
