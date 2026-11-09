"""STL and spectrogram of the same selected weekly reservoir filling series."""
import pandas as pd
import streamlit as st

from data_loader import select_data, select_analysis_area
from data_quality import reservoir_stl, reservoir_spectrogram

st.set_page_config(page_title="IND320 - Reservoir analysis", layout="wide")
st.title("Reservoir seasonality")
st.session_state.setdefault("chosen_area_type", "EL")
st.session_state.setdefault("chosen_months", ("2015-01", "2024-12"))
if st.button("Use NO3, 2015–2024"):
    st.session_state["chosen_area_type"] = "EL"
    st.session_state["area_type_control"] = "EL"
    st.session_state["chosen_area"] = ("EL", 3)
    st.session_state["analysis_area_EL"] = 3
    st.session_state["chosen_months"] = ("2015-01", "2024-12")
    st.session_state.pop("period_control", None)
selected, area_type, start, end = select_data()
area, number, region = select_analysis_area(selected, area_type)
label = region or f"{area_type} {number}"
filling = area.set_index("date")["filling_ratio"] * 100
st.caption(f"{label}: {len(filling)} weekly measurements. Both tabs use the same series.")
if len(filling) < 104:
    st.info("Select at least two years in the sidebar. A longer period makes annual seasonality easier to assess.")
    st.stop()

stl_tab, spectrum_tab = st.tabs(["STL", "Spectrogram"])
with stl_tab:
    a, b, c = st.columns(3)
    seasonal = a.number_input("Seasonal smoother", min_value=7, max_value=53, value=7, step=2)
    trend = b.number_input("Trend smoother (weeks)", min_value=53, max_value=521, value=105, step=2)
    robust = c.checkbox("Robust fitting", value=True)
    try:
        figure, components = reservoir_stl(filling, int(seasonal), int(trend), robust, f"{label} reservoir filling")
        st.pyplot(figure)
        st.caption(
            "Observed filling = trend + seasonal component + residual. The annual period is approximated by 52 weeks. "
            "Robust fitting downweights large residuals. Components near the ends of the series are less stable."
        )
        with st.expander("Decomposition values"):
            st.dataframe(components, width="stretch")
    except ValueError as error:
        st.error(str(error))
with spectrum_tab:
    a, b = st.columns(2)
    window = a.number_input("Window length (weeks)", min_value=8, max_value=len(filling), value=min(104, len(filling)), step=1)
    overlap = b.number_input("Window overlap (weeks)", min_value=0, max_value=int(window)-1, value=min(78, int(window)-1), step=1)
    try:
        figure, summary = reservoir_spectrogram(filling, int(window), int(overlap), f"{label} filling spectrogram")
        st.pyplot(figure)
        st.caption(
            f"Frequency resolution: {summary['frequency_resolution_cycles_per_year']:.3f} cycles/year. "
            "The dashed line marks annual variation. Colour is STFT magnitude in percentage points. "
            "Only complete windows are used, so the spectrogram does not cover the series endpoints."
        )
    except ValueError as error:
        st.error(str(error))
