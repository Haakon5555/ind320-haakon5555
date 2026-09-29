"""Home page of the app. Start it with: python -m streamlit run app.py"""

import streamlit as st

st.set_page_config(page_title="IND320 - Dashboard basics", layout="wide")

st.title("Dashboard basics")
st.write("This app shows weekly data about the water reservoirs in Norway, from 1995 to 2026.")
st.write(
    "Filling level tells how full the reservoirs are. "
    "Stored energy tells how much energy the water holds, measured in TWh."
)

# Streamlit makes the sidebar menu from app.py and the three files in pages/.
st.markdown("Use the menu on the left to open **Data**, **Plots** or **About**.")
