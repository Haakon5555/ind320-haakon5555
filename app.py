"""Home page for IND320 part 1. Run with: python -m streamlit run app.py."""

import streamlit as st

st.set_page_config(page_title="IND320 · Dashboard basics", layout="wide")
st.title("Dashboard basics")
st.write("Exploring Norwegian reservoir data.")
st.info("Starter app: use the sidebar to visit Data, Plots and About.")

# Streamlit adds the Python files in pages/ to the sidebar automatically.
# TODO: Add a short introduction after we have explored the data together.
