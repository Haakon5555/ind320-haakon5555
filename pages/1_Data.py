"""Starter for the required table page."""

import streamlit as st

st.set_page_config(page_title="IND320 · Data", layout="wide")
st.title("Reservoir data")
st.info("The data table will be added during the assignment walkthrough.")

# TODO: Read the local reservoirs.csv using a function with @st.cache_data.
# The original is in ../../01_grunnlag/prosjekt_del_1/ relative to app.py.
# Resolve paths from __file__ when implementing the loader, not from cwd.
# TODO: Decide how dates, area types and area numbers identify each series.
# TODO: Select the first month after sorting the chosen series by date.
# TODO: Build a table with one row per imported column and display
# its time series with st.column_config.LineChartColumn().
# Discuss how to represent identifiers and non-numeric columns explicitly.
