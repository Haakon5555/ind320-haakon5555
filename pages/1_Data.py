"""One row per available area, with weekly trends from the NVE API."""

import pandas as pd
import streamlit as st

from data_loader import select_data

st.set_page_config(page_title="IND320 - Data", layout="wide")
st.title("Reservoir data")
selected_data, area_type, start_date, end_date = select_data()
st.write("Choose the area type and period in the sidebar. Each row is one area.")

measurements = {
    "filling_ratio": ("Filling level (%)", 100),
    "capacity_twh": ("Capacity (TWh)", 1),
    "stored_energy_twh": ("Stored energy (TWh)", 1),
    "previous_week_filling_ratio": ("Previous week (%)", 100),
    "change_in_filling_ratio": ("Weekly change (pp)", 100),
}

# Each list is a time series for one area, ordered from the oldest week.
rows = []
for number, area in selected_data.groupby("area_number"):
    row = {"Area": f"{area_type} {number}", "Weeks": len(area)}
    for column, (label, multiplier) in measurements.items():
        row[label] = (area[column] * multiplier).tolist()
    rows.append(row)

st.dataframe(
    pd.DataFrame(rows),
    column_config={
        label: st.column_config.LineChartColumn(
            label, width="medium",
            help="Weekly values in date order. Each small chart has its own scale.",
        )
        for label, multiplier in measurements.values()
    },
    hide_index=True,
    width="stretch",
)
st.caption(
    "The small charts show the five measurements for each area. "
    "Each chart has its own scale. Use Plots to compare areas on a shared scale. "
    "A weekly change of 1 pp means one percentage point."
)

with st.expander("Weekly values and dates"):
    # Preserve the original values. Year 0001 is not a real publication date.
    table = selected_data.copy()
    table["next_publication_date"] = table["next_publication_date"].replace(
        "0001-01-01T00:00:00", "Not reported"
    )
    st.dataframe(table, hide_index=True, width="stretch")
    st.caption(
        "The table uses the API's fractions, so 0.8 means 80%. "
        "The date identifies the week. ISO year and ISO week are kept as reported. "
        "Not reported replaces the API's year 0001 placeholder."
    )
