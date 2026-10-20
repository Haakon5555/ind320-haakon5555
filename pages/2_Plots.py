"""Plots for every available area number of the selected NVE area type."""

import matplotlib.dates as mdates
from matplotlib.figure import Figure
import streamlit as st

from data_loader import select_data

st.set_page_config(page_title="IND320 - Plots", layout="wide")
st.title("Reservoir plots")
selected_data, area_type, start_date, end_date = select_data()

# The five measurement columns: title, unit and what to multiply with.
# Fractions are multiplied by 100 to show percent.
measurements = {
    "filling_ratio": ("Filling level", "%", 100),
    "capacity_twh": ("Capacity", "TWh", 1),
    "stored_energy_twh": ("Stored energy", "TWh", 1),
    "previous_week_filling_ratio": ("Previous week's filling level", "%", 100),
    "change_in_filling_ratio": ("Weekly change", "percentage points", 100),
}

# Keep the column menu from part 1, including the dates and labels.
combined_option = "All columns together"
columns = [combined_option, *selected_data.columns]
selected_column = st.selectbox(
    "Column", options=columns, index=columns.index("filling_ratio"),
    format_func=lambda name: name if name == combined_option else name.replace("_", " ").capitalize(),
)

st.caption(f"{len(selected_data)} observations across {selected_data['area_number'].nunique()} areas")

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
        fig = Figure(figsize=(10, 9))
        axes = fig.subplots(3, 1, sharex=True)
        fig.suptitle(f"{area_type} areas, all measurements")
        for ax, (group, axis_label) in zip(axes, groups):
            for color, (number, area) in enumerate(selected_data.groupby("area_number")):
                for position, column in enumerate(group):
                    title, unit, multiplier = measurements[column]
                    ax.plot(
                        area["date"], area[column] * multiplier,
                        color=f"C{color}", linewidth=1.2,
                        label=f"{area_type} {number}, {title}",
                        linestyle="--" if position else "-",
                        marker="o" if len(area) <= 16 else None,
                    )
            ax.set_ylabel(axis_label)
            ax.legend(loc="best", fontsize=7, ncol=2)
        # Zero line in the bottom panel, to see if the level went up or down.
        axes[-1].axhline(0, color="gray", linewidth=0.7, linestyle=":")
        st.caption(
            "The five measurements are split into three panels because they have different units. "
            "Dates and labels are shown in the table below the figure."
        )
    else:
        # One measurement alone, with its own unit on the y-axis.
        fig = Figure(figsize=(10, 4.5))
        ax = fig.subplots()
        axes = [ax]
        title, unit, multiplier = measurements[selected_column]
        for number, area in selected_data.groupby("area_number"):
            ax.plot(
                area["date"], area[selected_column] * multiplier,
                linewidth=1.6, label=f"{area_type} {number}",
                marker="o" if len(area) <= 16 else None,
            )
        ax.legend(title="Area", ncol=3, fontsize=8)
        ax.set_title(title)
        ax.set_ylabel(f"{title} ({unit})")

    axes[-1].set_xlabel("Date")
    for ax in axes:
        # The x-axis covers the whole chosen period.
        # Convert the dates to the numbers Matplotlib uses for axis limits.
        ax.set_xlim(
            float(mdates.date2num(start_date)),
            float(mdates.date2num(end_date)),
        )
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
        metadata_columns = [column for column in selected_data.columns if column not in measurements]
    else:
        st.info("This column is a date or a label, so the values are shown in a table.")
        metadata_columns = list(dict.fromkeys(["date", "area_type", "area_number", selected_column]))
    metadata = selected_data[metadata_columns].copy()
    if "next_publication_date" in metadata.columns:
        # Year 0001 is an API placeholder, not a real date.
        metadata["next_publication_date"] = metadata["next_publication_date"].replace(
            "0001-01-01T00:00:00", "Not reported"
        )
        st.caption("'Not reported' means that the API has no real publication date.")
    st.dataframe(metadata, hide_index=True, width="stretch")
