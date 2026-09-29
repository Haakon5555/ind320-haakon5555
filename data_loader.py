"""Reads reservoirs.csv. Used by both the Data page and the Plots page."""

from pathlib import Path
import pandas as pd
import streamlit as st

# st.cache_data is a built-in saving function in streamlit. The function saves the result, so that the CSV is only read the first time.
@st.cache_data
def load_data():
    # The path starts from this file, so it works both locally and on Streamlit Cloud.
    csv_path = Path(__file__).resolve().parent / "data/reservoirs.csv"
    data = pd.read_csv(csv_path)

    # Same English column names as in the notebook.
    data = data.rename(columns={
        "dato_Id": "date",
        "omrType": "area_type",
        "omrnr": "area_number",
        "iso_aar": "iso_year",
        "iso_uke": "iso_week",
        "fyllingsgrad": "filling_ratio",
        "kapasitet_TWh": "capacity_twh",
        "fylling_TWh": "stored_energy_twh",
        "neste_Publiseringsdato": "next_publication_date",
        "fyllingsgrad_forrige_uke": "previous_week_filling_ratio",
        "endring_fyllingsgrad": "change_in_filling_ratio",
    })

    # The dates are text in the file. Make them real dates and sort by date.
    data["date"] = pd.to_datetime(data["date"])
    return data.sort_values("date")
