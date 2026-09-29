"""Plots page: choose a column and a range of months, and plot the data for Norway."""

import matplotlib.dates as mdates
from matplotlib.figure import Figure
import pandas as pd
import streamlit as st

from data_loader import load_data

st.set_page_config(page_title="IND320 - Plots", layout="wide")
st.title("Reservoir plots")
st.write("Weekly values for Norway (NO 0).")

# Same cached data as on the Data page.
reservoirs = load_data()
norway = reservoirs.loc[
    (reservoirs["area_type"] == "NO") & (reservoirs["area_number"] == 0)
]

# The five measurement columns: title, unit and what to multiply with.
# Fractions are multiplied by 100 to show percent.
measurements = {
    "filling_ratio": ("Filling level", "%", 100),
    "capacity_twh": ("Capacity", "TWh", 1),
    "stored_energy_twh": ("Stored energy", "TWh", 1),
    "previous_week_filling_ratio": ("Previous week's filling level", "%", 100),
    "change_in_filling_ratio": ("Weekly change", "percentage points", 100),
}

# Drop-down menu with every CSV column, plus one choice for all columns together.
combined_option = "All columns together"
columns = [combined_option, *reservoirs.columns]
selected_column = st.selectbox(
    "Column", options=columns, index=columns.index("filling_ratio"),
    format_func=lambda name: name if name == combined_option else name.replace("_", " ").capitalize(),
)

# Slider with all months written as YYYY-MM. Both handles start on the first month.
months = norway["date"].dt.strftime("%Y-%m").drop_duplicates().tolist()
start_month, end_month = st.select_slider(
    "Months", options=months, value=(months[0], months[0]),
    help="Move the two handles to choose the first and last month.",
)

# Keep the weeks from the start of the first month to the end of the last month.
start_date = pd.Period(start_month, freq="M").start_time
end_date = pd.Period(end_month, freq="M").end_time
selected_data = norway.loc[norway["date"].between(start_date, end_date)]
st.caption(f"{len(selected_data)} weekly observations from {start_month} to {end_month}")

if selected_column == combined_option or selected_column in measurements:
    # The figure is made with Figure() and shown with st.pyplot(fig) further down.
    if selected_column == combined_option:
        # The units are different, so the columns are split into three panels
        # with the same date axis: percent, TWh and percentage points.
        groups = [
            (["filling_ratio", "previous_week_filling_ratio"], "Filling level (%)"),
            (["capacity_twh", "stored_energy_twh"], "Energy (TWh)"),
            (["change_in_filling_ratio"], "Weekly change\n(percentage points)"),
        ]
        fig = Figure(figsize=(7, 8))
        axes = fig.subplots(3, 1, sharex=True)
        fig.suptitle("Norway: all measurements")
        for ax, (group, axis_label) in zip(axes, groups):
            for column in group:
                title, unit, multiplier = measurements[column]
                ax.plot(
                    selected_data["date"], selected_data[column] * multiplier,
                    linewidth=1.6, label=title,
                    # Dashed line for last week's level, since it lies close to this week's.
                    linestyle="--" if column == "previous_week_filling_ratio" else "-",
                    # Show the points when there are few of them.
                    marker="o" if len(selected_data) <= 16 else None,
                )
            ax.set_ylabel(axis_label)
            ax.legend(loc="best", fontsize=8)
        # Zero line in the bottom panel, to see if the level went up or down.
        axes[-1].axhline(0, color="gray", linewidth=0.7, linestyle=":")
        st.caption(
            "The five measurements are split into three panels because they have different units. "
            "Dates and labels are shown in the table below the figure."
        )
    else:
        # One measurement alone, with its own unit on the y-axis.
        fig = Figure(figsize=(7, 4.5))
        ax = fig.subplots()
        axes = [ax]
        title, unit, multiplier = measurements[selected_column]
        ax.plot(
            selected_data["date"], selected_data[selected_column] * multiplier,
            color="tab:blue", linewidth=1.6,
            marker="o" if len(selected_data) <= 16 else None,
        )
        ax.set_title(f"Norway: {title}")
        ax.set_ylabel(f"{title} ({unit})")

    axes[-1].set_xlabel("Date")
    for ax in axes:
        # The x-axis covers the whole chosen period.
        ax.set_xlim(start_date, end_date)
        ax.grid(alpha=0.2)

    # Let Matplotlib pick a few date labels, so they do not overlap.
    locator = mdates.AutoDateLocator(minticks=3, maxticks=6)
    axes[-1].xaxis.set_major_locator(locator)
    axes[-1].xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    fig.tight_layout()
    st.pyplot(fig)

if selected_column == combined_option or selected_column not in measurements:
    # Dates and labels are shown in a table. A line plot of them would not make sense.
    if selected_column == combined_option:
        st.subheader("Dates and labels")
        metadata_columns = [column for column in reservoirs.columns if column not in measurements]
    else:
        st.info("This column is a date or a label, so the values are shown in a table.")
        metadata_columns = ["date"] if selected_column == "date" else ["date", selected_column]
    metadata = selected_data[metadata_columns].copy()
    if "next_publication_date" in metadata.columns:
        # Year 0001 is a placeholder in the file, so there is no real date.
        metadata["next_publication_date"] = metadata["next_publication_date"].replace(
            "0001-01-01T00:00:00", "Not reported"
        )
        st.caption("'Not reported' means that the file has no real publication date.")
    st.dataframe(metadata, hide_index=True, width="stretch")
