"""NVE data, shared period controls and MongoDB queries for the app."""

import os
import pandas as pd
import requests
import streamlit as st
from pymongo import MongoClient
from streamlit.errors import StreamlitSecretNotFoundError

NVE_URL = "https://biapi.nve.no/magasinstatistikk/api/Magasinstatistikk/HentOffentligData"

# Reuse one download across both pages for one hour.
@st.cache_data(ttl=3600)
def load_data():
    response = requests.get(NVE_URL, timeout=30)
    response.raise_for_status()
    data = pd.DataFrame(response.json())

    # Same English column names as in the notebook.
    column_names = {
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
    }
    missing = set(column_names) - set(data.columns)
    if missing:
        raise ValueError(f"NVE response is missing columns {sorted(missing)}")
    data = data.rename(columns=column_names)

    # Keep the reported ISO year/week. A calendar year can differ from an ISO year.
    data["date"] = pd.to_datetime(data["date"])
    if data.empty or data["date"].isna().any():
        raise ValueError("NVE returned no usable measurement dates.")
    if data.duplicated(["date", "area_type", "area_number"]).any():
        raise ValueError("NVE returned duplicate dates for an area.")
    return data.sort_values(["date", "area_type", "area_number"]).reset_index(drop=True)


def select_data():
    """Download once, then use the same area and period choices on both pages."""
    try:
        reservoirs = load_data()
    except (requests.RequestException, ValueError) as error:
        st.error(f"Could not load the NVE data. {error}")
        st.stop()

    # Store choices separately from widget keys so they survive page changes.
    area_types = sorted(reservoirs["area_type"].unique())
    chosen_type = st.session_state.get("chosen_area_type", "NO")
    if chosen_type not in area_types:
        chosen_type = area_types[0]
    with st.sidebar:
        area_type = st.radio(
            "Area type", area_types, index=area_types.index(chosen_type),
            help="EL is electricity price areas, NO is Norway, VASS is water regions.",
        )
        months = reservoirs["date"].dt.strftime("%Y-%m").drop_duplicates().tolist()
        saved_months = st.session_state.get("chosen_months", (months[max(0, len(months) - 12)], months[-1]))
        # A refreshed API response can change the available dates.
        if any(month not in months for month in saved_months):
            saved_months = (months[0], months[-1])
        start_month, end_month = st.select_slider(
            "Months", options=months, value=saved_months,
            help="Both end months are included. NVE supplies the full history, then the app selects this period.",
        )
        st.caption(
            "NVE provides the full history without date parameters. "
            "The selected period is filtered after download."
        )
    st.session_state["chosen_area_type"] = area_type
    st.session_state["chosen_months"] = (start_month, end_month)
    start_date = pd.Period(start_month, freq="M").start_time
    end_date = pd.Period(end_month, freq="M").end_time
    selected = reservoirs.loc[
        reservoirs["area_type"].eq(area_type)
        & reservoirs["date"].between(start_date, end_date)
    ].copy()
    if selected.empty:
        st.info("There are no measurements for this area type and period.")
        st.stop()
    st.caption(
        f"{area_type}, {start_month} to {end_month}. "
        f"Latest available measurement {reservoirs['date'].max():%d %B %Y}."
    )
    if area_type == "VASS":
        st.caption(
            "The current area list includes VASS 4, but the measurement API "
            "currently returns only VASS 1, 2 and 3."
        )
    return selected, area_type, start_date, end_date


@st.cache_resource
def transfer_collection():
    """Keep one MongoDB connection pool. Credentials never appear in page output."""
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        try:
            uri = st.secrets["MONGODB_URI"]
        except (KeyError, StreamlitSecretNotFoundError):
            raise ValueError("MongoDB connection is not configured.") from None
    client = MongoClient(uri, tz_aware=True, serverSelectionTimeoutMS=15000)
    return client["ind320"]["physical_flow_months"]


@st.cache_data(ttl=600)
def transfer_choices():
    """Return the connection/year combinations actually stored in MongoDB."""
    rows = transfer_collection().aggregate([
        {"$group": {"_id": {"connection": "$connection", "year": "$year"}}}
    ])
    return sorted((row["_id"]["connection"], row["_id"]["year"]) for row in rows)


@st.cache_data(ttl=600)
def transfer_sources(connection, year):
    """Identify the retrieval method saved with the selected year's documents."""
    rows = transfer_collection().find(
        {"connection": connection, "year": int(year)}, {"source_method": 1}
    )
    # Earlier documents were created from the original website exports.
    return sorted({row.get("source_method", "ENTSO-E website CSV exports") for row in rows})


@st.cache_data(ttl=600)
def transfer_totals(connection, year):
    """Sum interval energy in MongoDB before sending the annual totals to the app."""
    rows = transfer_collection().aggregate([
        {"$match": {"connection": connection, "year": int(year)}},
        {"$unwind": "$values"},
        {"$group": {"_id": "$values.direction", "energy_mwh": {"$sum": "$values.energy_mwh"}}},
    ])
    return {row["_id"]: row["energy_mwh"] / 1_000_000 for row in rows}


@st.cache_data(ttl=600)
def transfer_months(connection, year, months):
    """Query only the selected months and the fields needed by the line plot."""
    rows = transfer_collection().aggregate([
        {"$match": {"connection": connection, "year": int(year), "month": {"$in": list(months)}}},
        {"$unwind": "$values"},
        {"$project": {"_id": 0, "start_utc": "$values.start_utc",
                      "direction": "$values.direction", "power_mw": "$values.power_mw"}},
        {"$sort": {"start_utc": 1}},
    ])
    data = pd.DataFrame(list(rows))
    if not data.empty:
        data["start_utc"] = pd.to_datetime(data["start_utc"], utc=True)
    return data
