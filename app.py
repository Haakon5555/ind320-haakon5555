"""Entry point and page order for the IND320 dashboard."""
import streamlit as st

st.set_page_config(page_title="IND320 - Data quality", layout="wide")


def overview():
    st.title("Norwegian reservoirs, weather and electricity transfers")
    st.write("Explore NVE reservoir filling, ERA5 weather and cross-border electricity flows.")
    st.markdown(
        "**Data** and **Plots** show reservoir measurements. "
        "**Reservoir analysis** examines their seasonal patterns with STL and a spectrogram. "
        "**Weather quality** highlights unusual precipitation and temperature. "
        "**Transfers** shows physical electricity flows from MongoDB."
    )
    st.write("Reservoir and weather analyses share the area and period selected in the sidebar. NO3 weather for 2024 is the worked example.")


page = st.navigation([
    st.Page(overview, title="Overview", default=True),
    st.Page("pages/1_Data.py", title="Data"),
    st.Page("pages/2_Plots.py", title="Plots"),
    st.Page("pages/5_Reservoir_analysis.py", title="Reservoir analysis"),
    st.Page("pages/6_Weather_quality.py", title="Weather quality"),
    st.Page("pages/3_Transfers.py", title="Transfers"),
    st.Page("pages/4_About.py", title="About"),
])
page.run()
