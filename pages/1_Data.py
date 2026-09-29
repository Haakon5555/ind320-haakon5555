"""Data page: table with the first month of data, one row per CSV column."""

import pandas as pd
import streamlit as st

from data_loader import load_data

st.set_page_config(page_title="IND320 - Data", layout="wide")
st.title("Reservoir data")

# load_data is cached, so the CSV is not read again on every rerun.
reservoirs = load_data()

# The file has nine areas. NO 0 is the total for Norway, and the app shows that one.
norway = reservoirs.loc[
    (reservoirs["area_type"] == "NO") & (reservoirs["area_number"] == 0)
]

# Find the first month in the data (January 1995) and keep only those weeks.
first_month = norway["date"].min().to_period("M")
month_data = norway.loc[norway["date"].dt.to_period("M") == first_month]
st.subheader(f"Norway (NO 0), {first_month.strftime('%B %Y')}")
st.write("Each row in the table is one column from the CSV file.")
st.caption("Weeks: " + ", ".join(month_data["date"].dt.strftime("%d %b %Y")))

# These five columns are measurements. Only they get a line chart.
measurement_columns = [
    "filling_ratio", "capacity_twh", "stored_energy_twh",
    "previous_week_filling_ratio", "change_in_filling_ratio",
]

# Build the table with one row for each CSV column.
rows = []
for column in month_data.columns:
    values = month_data[column]

    # Make a text version of the values to show in the table.
    if column == "date":
        display_values = values.dt.strftime("%Y-%m-%d").tolist()
    elif column == "next_publication_date":
        # Year 0001 is a placeholder in the file, so there is no real date.
        display_values = ["Not reported" if str(v).startswith("0001-") else str(v) for v in values]
    elif pd.api.types.is_numeric_dtype(values):
        display_values = [f"{v:.6g}" for v in values]
    else:
        display_values = values.astype(str).tolist()

    rows.append({
        "Column": column,
        # LineChartColumn needs a list of numbers. The other rows get no chart.
        "Trend": values.tolist() if column in measurement_columns else None,
        "Weekly values": display_values,
    })

# LineChartColumn draws the list of numbers as a small line chart in each row.
st.dataframe(
    pd.DataFrame(rows),
    column_config={
        "Column": st.column_config.TextColumn(width="medium"),
        "Weekly values": st.column_config.ListColumn(width="medium"),
        "Trend": st.column_config.LineChartColumn(
            "Weekly trend", width=130,
            help="The four weekly values in date order. Each row has its own scale.",
        ),
    },
    hide_index=True,
    height=430,
    width="stretch",
)
st.caption(
    "Filling values are fractions (0.8 = 80%). Capacity and stored energy are in TWh. "
    "Each small chart has its own scale. "
    "'Not reported' means that the file has no real publication date."
)
