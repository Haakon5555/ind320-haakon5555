"""Home page of the app. Start it with: python -m streamlit run app.py"""

import streamlit as st

st.set_page_config(page_title="IND320 - Data sources", layout="wide")

st.title("Norwegian reservoirs and electricity transfers")
st.write(
    "Weekly reservoir data comes directly from NVE. "
    "Cross-border electricity flows are queried from MongoDB."
)
st.write(
    "Filling level tells how full the reservoirs are. "
    "Stored energy tells how much energy the water holds, measured in TWh."
)

# Streamlit makes the sidebar menu from app.py and the four files in pages/.
st.markdown("Use the menu on the left to open **Data**, **Plots**, **Transfers** or **About**.")
st.write("Data and Plots share the area type and period selected in the sidebar.")
