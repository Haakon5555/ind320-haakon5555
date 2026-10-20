"""Physical flows queried directly from the curated MongoDB collection."""

import calendar
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import streamlit as st
from pymongo.errors import PyMongoError

from data_loader import transfer_choices, transfer_totals, transfer_months, transfer_sources

st.set_page_config(page_title="IND320 - Transfers", layout="wide")
st.title("Cross-border electricity transfers")
st.caption("Import and export are seen from Norway. Dates and months use UTC.")

try:
    choices = transfer_choices()
    if not choices:
        st.info("No transfer data has been uploaded to MongoDB yet.")
        st.stop()
    connections = sorted({connection for connection, year in choices})
    left, right = st.columns(2)
    with left:
        connection = st.radio(
            "Connection", connections,
            index=connections.index("NO2 / NL") if "NO2 / NL" in connections else 0,
            horizontal=True,
        )
        years = sorted({year for name, year in choices if name == connection})
        year = st.selectbox("Year", years, index=len(years) - 1)
        sources = transfer_sources(connection, year)
        totals = transfer_totals(connection, year)
        amounts = [totals.get(direction, 0.0) for direction in ("Import", "Export")]
        if sum(amounts) > 0:
            fig, ax = plt.subplots(figsize=(5, 4))
            labels = [
                f"{direction}\n{value:.3f} TWh"
                for direction, value in zip(("Import", "Export"), amounts)
            ]
            ax.pie(amounts, labels=labels, autopct="%.1f%%", startangle=90,
                   colors=["tab:orange", "tab:blue"])
            ax.set_title(f"{connection}, {year}")
            fig.tight_layout()
            st.pyplot(fig, width=320)
            plt.close(fig)
        else:
            st.info("No energy was transferred for this connection and year.")
        st.caption("Annual energy is the sum of power multiplied by interval duration.")
    with right:
        months = st.pills(
            "Months", list(range(1, 13)), selection_mode="multi", default=[1],
            format_func=lambda month: calendar.month_abbr[month],
            wrap=True,
        )
        if not months:
            st.info("Select at least one month.")
        else:
            data = transfer_months(connection, year, tuple(sorted(months)))
            if data.empty:
                st.info("No measurements for the selected months.")
            else:
                # Empty hours remain gaps, so non-adjacent selected months are not joined.
                grid = pd.date_range(
                    data["start_utc"].min(), data["start_utc"].max(), freq="h"
                )
                fig, ax = plt.subplots(figsize=(8, 4))
                for direction, color in (("Import", "tab:orange"), ("Export", "tab:blue")):
                    series = data.loc[data["direction"].eq(direction)].set_index("start_utc")
                    ax.plot(grid, series["power_mw"].reindex(grid),
                            label=direction, color=color, linewidth=0.8)
                ax.set(title=f"{connection}, {year}", xlabel="Date (UTC)",
                       ylabel="Physical flow (MW)")
                locator = mdates.AutoDateLocator(minticks=3, maxticks=6)
                ax.xaxis.set_major_locator(locator)
                ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
                ax.legend()
                ax.grid(alpha=0.2)
                fig.tight_layout()
                st.pyplot(fig)
                plt.close(fig)
                st.caption(f"{len(data):,} hourly observations across both directions.")
except (PyMongoError, ValueError):
    # Raw connection exceptions can contain hostnames or connection information.
    st.error("Could not read transfer data from MongoDB. Check connection settings and access.")
    st.stop()

with st.expander("Data source and preparation"):
    st.markdown(
        "Source is [ENTSO-E Transparency Platform]"
        "(https://transparency.entsoe.eu/transmission/physicalFlows), "
        "Cross-Border Physical Flows, TR12.1.G. The complete calendar years 2024 "
        "and 2025 are represented as hourly mean MW in UTC. "
        "Nine international connections are included."
    )
    st.write("Retrieval method for this connection and year: " + ", ".join(sources) + ".")
    st.write(
        "The notebook checks coverage, duplicates and missing values, writes the "
        "data to Cassandra through Spark, reads it back and calculates interval energy. "
        "These prepared records are stored in MongoDB and queried directly by this page. "
        "Query results are cached for ten minutes. Physical flows describe electricity "
        "crossing a border, not electricity production."
    )
