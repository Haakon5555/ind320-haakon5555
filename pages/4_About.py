"""About page: short text about the project and where the data comes from."""

import streamlit as st

st.set_page_config(page_title="IND320 - About", layout="wide")
st.title("About this project")
st.write("IND320 Data to Decision, autumn 2026. Project work, part 2.")
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
    "The notebook uses the REST API when a token is configured, or the preserved "
    "annual CSV exports while access is pending. The Transfers source panel shows "
    "the method used for the selected connection and year. Spark stores and reads the data through "
    "Cassandra, then the notebook uploads the prepared records to MongoDB. "
    "The app queries MongoDB directly and caches query results for ten minutes."
)
