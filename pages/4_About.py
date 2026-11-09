"""About page: short text about the project and where the data comes from."""

import streamlit as st

st.set_page_config(page_title="IND320 - About", layout="wide")
st.title("About this project")
st.write("IND320 Data to Decision, autumn 2026. Project work, parts 1–3.")
st.write(
    "The app shows weekly data about Norwegian water reservoirs: "
    "filling level, capacity, stored energy and weekly change. "
    "Choose electricity price areas (EL), Norway (NO) or water regions (VASS). "
    "The areas overlap, so they must not be added together."
)
st.markdown(
    "Data from [NVE Magasinstatistikk]"
    "(https://www.nve.no/energi/analyser-og-statistikk/magasinstatistikk/). "
    "[API documentation](https://biapi.nve.no/magasinstatistikk/swagger/index.html)."
)
st.write(
    "The API download is cached for one hour and shared between Data and Plots. "
    "The documented endpoint has no date parameters, so the period is selected after download. "
    "This differs from the assignment's requested filtering during download."
)
st.caption("The app and the part 2 notebook use the NVE API instead of the CSV file from part 1.")
st.caption("The notebook in the repository has the analysis, the work log and the AI description.")
st.markdown(
    "Transfers shows physical electricity flows from "
    "[ENTSO-E Transparency Platform](https://transparency.entsoe.eu/). "
    "The notebook downloads the data from the ENTSO-E REST API. Spark stores and reads the data through "
    "Cassandra, then the notebook uploads the prepared records to MongoDB. "
    "The app queries MongoDB directly and caches query results for ten minutes."
)


st.subheader("Weather and data quality")
st.markdown(
    "Weather comes from the [Open-Meteo Historical Weather API]"
    "(https://open-meteo.com/en/docs/historical-weather-api), using "
    "[ERA5](https://doi.org/10.24381/cds.adbb2d47) from the Copernicus Climate Change Service. "
    "[Open-Meteo software citation](https://doi.org/10.5281/zenodo.7970649). "
    "Weather data are provided under CC BY 4.0."
)
st.write(
    "The notebook samples 1000 locations separately in each of three course region groups "
    "and five electricity price areas. The app averages all locations within the selected area. "
    "Weather values are reanalysis estimates, not independent station observations."
)
st.write(
    "Precipitation flags use a DCT high-pass filter and robust SPC limits. "
    "Temperature anomalies use Local Outlier Factor. STL and a spectrogram "
    "describe weekly reservoir filling. Flagged values are kept for inspection."
)
st.caption("Part 3 was developed with AI assistance. The notebook documents the methods, checks and limitations.")
