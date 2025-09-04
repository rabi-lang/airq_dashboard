import os
import pandas as pd
import plotly.express as px
import streamlit as st
from st_aggrid import AgGrid
from zoneinfo import ZoneInfo

st.set_page_config(page_title="Air Quality – Live City Monitor", layout="wide")

# Heading
st.title("Real-Time Air Quality Across Australian Cities")
st.caption("Source: World Air Quality Index (AQICN / WAQI). Attribution required. Times in AWST (as of 01:56 AM, Sep 05, 2025).")

@st.cache_data
def load_latest():
    if os.path.exists("data/aqi_latest.csv"):
        try:
            df = pd.read_csv("data/aqi_latest.csv", parse_dates=["observed_at_utc"])
            return df
        except Exception as e:
            st.error(f"Error loading aqi_latest.csv: {e}")
            st.stop()
    st.error("Run `python fetch_aqicn.py` first to create data/aqi_latest.csv")
    st.stop()

@st.cache_data
def load_log():
    if os.path.exists("data/aqi_log.csv"):
        try:
            return pd.read_csv("data/aqi_log.csv", parse_dates=["observed_at_utc"])
        except Exception as e:
            st.warning(f"Error loading aqi_log.csv: {e}")
            return None
    return None

# Load data
df_latest = load_latest()
df_log = load_log()

# Time conversion to Perth timezone
if not df_latest.empty:
    df_latest["observed_at_awst"] = df_latest["observed_at_utc"].dt.tz_convert("Australia/Perth")
if df_log is not None and not df_log.empty:
    df_log["observed_at_awst"] = df_log["observed_at_utc"].dt.tz_convert("Australia/Perth")

# Sidebar controls
cities = sorted(df_latest["city"].dropna().unique()) if not df_latest.empty else []
pick_cities = st.sidebar.multiselect("Cities", options=cities, default=cities[:1] if cities else [])
pollutants = [c for c in ["pm25", "pm10", "o3", "no2", "so2", "co", "nh3"] if c in df_latest.columns]
pick_pol = st.sidebar.selectbox("Pollutant detail", pollutants if pollutants else [None])
if df_log is not None and not df_log.empty:
    date_range = st.sidebar.date_input(
        "Date Range",
        value=(df_log["observed_at_awst"].min().date(), df_log["observed_at_awst"].max().date())
    )
else:
    date_range = None

# Real-time refresh button
if st.sidebar.button("Refresh Data"):
    try:
        os.system("python fetch_aqicn.py")
        st.experimental_rerun()
    except Exception as e:
        st.error(f"Refresh failed: {e}")

# Filter data
filtered = df_latest[df_latest["city"].isin(pick_cities)].copy() if not df_latest.empty else pd.DataFrame()
if df_log is not None and not df_log.empty and date_range:
    df_log = df_log[
        (df_log["observed_at_awst"].dt.date >= date_range[0]) &
        (df_log["observed_at_awst"].dt.date <= date_range[1]) &
        (df_log["city"].isin(pick_cities))
    ].copy()

# Tabs for storytelling (Overview, Trends & Discovery, Insights)
tab1, tab2, tab3 = st.tabs(["Overview", "Trends & Discovery", "Insights"])

with tab1:
    # KPI tiles
    if not filtered.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("Cities monitored", f"{filtered['city'].nunique():,}")
        risk = len(filtered[filtered["aqi"] >= 151])
        col2.metric("Unhealthy or worse", f"{risk:,}")
        col3.metric("Latest timestamp (AWST)", filtered["observed_at_awst"].max().strftime("%Y-%m-%d %H:%M"))
    else:
        st.warning("No data available for KPIs.")

    # Map with heatmap and clustering
    if not filtered.empty and "lat" in filtered.columns and "lon" in filtered.columns:
        filtered_map = filtered.dropna(subset=["lat", "lon"])
        if not filtered_map.empty:
            st.subheader("Map: City AQI (bubble sized by AQI; colored by category)")
            fig_map = px.scatter_mapbox(
                filtered_map,
                lat="lat", lon="lon", color="aqi_category", size="aqi",
                hover_data={
                    "city": True, "aqi": True, "aqi_category": True, "dominentpol": True,
                    "observed_at_awst": True,
                    "health_note": filtered_map.apply(lambda row: f"Health Risk: {row['aqi_category']}" if pd.notna(row['aqi_category']) else "Unknown", axis=1)
                },
                zoom=3, height=500,
                color_discrete_sequence=px.colors.qualitative.Safe
            )
            if pick_pol and pick_pol in filtered_map.columns:
                fig_heat = px.density_mapbox(
                    filtered_map, lat="lat", lon="lon", z=pick_pol, radius=20,
                    center={"lat": -25.2744, "lon": 133.7751}, zoom=3,
                    mapbox_style="open-street-map", height=500
                )
                fig_map.add_trace(fig_heat.data[0])
            fig_map.update_traces(cluster=dict(enabled=True)) if len(pick_cities) > 20 else None
            fig_map.update_layout(mapbox_style="open-street-map", margin=dict(l=0, r=0, t=0, b=0))
            st.plotly_chart(fig_map, use_container_width=True)
        else:
            st.warning("No valid location data for map.")
    else:
        st.warning("No valid location data for map.")

    # Historical map animation
    if df_log is not None and not df_log.empty and "lat" in df_log.columns and "lon" in df_log.columns:
        df_log_map = df_log.dropna(subset=["lat", "lon"])
        if not df_log_map.empty:
            st.subheader("Historical AQI Map Animation")
            df_log_map["date"] = df_log_map["observed_at_awst"].dt.date
            fig_anim = px.scatter_mapbox(
                df_log_map, lat="lat", lon="lon", color="aqi_category", size="aqi",
                hover_data=["city", "aqi", "aqi_category", "dominentpol", "observed_at_awst"],
                animation_frame="date", zoom=3, height=500,
                mapbox_style="open-street-map",
                color_discrete_sequence=px.colors.qualitative.Safe
            )
            st.plotly_chart(fig_anim, use_container_width=True)
        else:
            st.info("No valid historical location data for animation.")
    else:
        st.info("No historical data available for animation.")

with tab2:
    # Bar chart
    if not filtered.empty and "aqi" in filtered.columns:
        st.subheader("AQI by City")
        fig_bar = px.bar(
            filtered.sort_values("aqi", ascending=False), x="city", y="aqi", color="aqi_category",
            color_discrete_sequence=px.colors.qualitative.Safe
        )
        fig_bar.update_layout(xaxis_title="", yaxis_title="AQI")
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.warning("No data available for bar chart.")

    # Time series
    if df_log is not None and not df_log.empty and "aqi" in df_log.columns:
        st.subheader("Trend: AQI Over Time (Local Log)")
        fig_ts = px.line(
            df_log.sort_values("observed_at_awst"), x="observed_at_awst", y="aqi", color="city",
            color_discrete_sequence=px.colors.qualitative.Safe
        )
        fig_ts.update_layout(xaxis_title="Time (AWST)", yaxis_title="AQI")
        st.plotly_chart(fig_ts, use_container_width=True)
    else:
        st.info("No log yet—run the fetcher a few times to build history.")

    # Correlation heatmap
    if not filtered.empty and all(p in filtered.columns for p in pollutants + ["aqi"]):
        st.subheader("Pollutant Correlations (Discovery)")
        corr = filtered[pollutants + ["aqi"]].corr()
        fig_corr = px.imshow(corr, text_auto=True, aspect="auto", color_continuous_scale="Viridis")
        st.plotly_chart(fig_corr, use_container_width=True)
    else:
        st.warning("Insufficient data for correlation heatmap.")

    # Pollutant detail table (interactive)
    if pick_pol and pick_pol in filtered.columns:
        st.subheader(f"{pick_pol.upper()} Concentration Snapshot")
        cols = ["city", "aqi", "aqi_category", "dominentpol", "observed_at_awst", pick_pol]
        filtered["avg_aqi"] = filtered.groupby("city")["aqi"].transform("mean") if not filtered.empty else pd.Series()
        AgGrid(
            filtered[cols + ["avg_aqi"]].sort_values(pick_pol, ascending=False),
            height=300, fit_columns=True
        )
    else:
        st.warning("No data available for pollutant table.")

    # Raw data explorer
    uploaded = st.sidebar.file_uploader("Upload Custom AQI CSV")
    if uploaded:
        st.subheader("Custom Data Table")
        df_custom = pd.read_csv(uploaded)
        st.dataframe(df_custom, use_container_width=True)

with tab3:
    # Insights and alerts
    st.subheader("Key Insights")
    if not filtered.empty:
        st.write("Based on data: High AQI in cities may be driven by dominant pollutants like PM2.5 or PM10. Recommendation: Monitor sensitive groups in high-risk areas.")
        for _, row in filtered.iterrows():
            if row["aqi"] > 150 and pd.notna(row["aqi"]):
                st.warning(f"Alert for {row['city']}: {row['aqi_category']} (AQI: {row['aqi']})")
    else:
        st.warning("No data available for insights.")

# Download button
if not filtered.empty:
    st.download_button(
        "Download Snapshot (CSV)", filtered.to_csv(index=False).encode("utf-8"), "aqi_snapshot.csv"
    )
else:
    st.warning("No data available to download.")

# Footer with references and version
st.markdown("""
---
**Developed by**:   
ICT605 Group Project Team – Semester 2, 2025.  
**Version: 2.0.0**
""")