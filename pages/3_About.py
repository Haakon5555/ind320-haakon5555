"""About page: short text about the project and where the data comes from."""

import streamlit as st

st.set_page_config(page_title="IND320 - About", layout="wide")
st.title("About this project")
st.write("IND320 Data to Decision, autumn 2026. Project work, part 1.")
st.write(
    "The app shows weekly data about Norwegian water reservoirs: "
    "filling level, capacity, stored energy and weekly change. "
    "The Data and Plots pages show the numbers for all of Norway (NO 0)."
)
# The app reads a CSV file that is stored in the repository. It is not live data.
st.markdown(
    "**Data source:** [reservoirs.csv from the IND320 course repository]"
    "(https://github.com/khliland/IND320/blob/main/D2Dbook/data/reservoirs.csv)."
)
st.write("The data goes from 8 January 1995 to 6 September 2026.")
st.caption("The notebook in the repository has the analysis, the work log and the AI description.")
