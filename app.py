import os, pandas as pd, plotly.express as px, streamlit as st
from zoneinfo import ZoneInfo

st.set_page_config(page_title="Air Quality – Live City Monitor", layout="wide")

@st.cache_data
def load_latest():
    if os.path.exists("data/aqi_latest.csv"):
        df = pd.read_csv("data/aqi_latest.csv", parse_dates=["observed_at_utc"])
        return df
    st.error("Run `python fetch_aqicn.py` first to create data/aqi_latest.csv")
    st.stop()

@st.cache_data
def load_log():
    if os.path.exists("data/aqi_log.csv"):
        return pd.read_csv("data/aqi_log.csv", parse_dates=["observed_at_utc"])
    return None

df_latest = load_latest()
df_log = load_log()

st.title("Real-Time Air Quality Across Cities")
st.caption("Source: World Air Quality Index (AQICN / WAQI). Attribution required. Times converted to Australia/Perth (AWST).")

# Time conversion (station-local timestamps have offsets; convert to Perth)
df_latest["observed_at_awst"] = df_latest["observed_at_utc"].dt.tz_convert("Australia/Perth")

# Sidebar controls
cities = sorted(df_latest["city"].dropna().unique())
pick_cities = st.sidebar.multiselect("Cities", options=cities, default=cities)
pollutants = [c for c in ["pm25","pm10","o3","no2","so2","co","nh3"] if c in df_latest.columns]
pick_pol = st.sidebar.selectbox("Pollutant detail", pollutants if pollutants else [None])

filtered = df_latest[df_latest["city"].isin(pick_cities)].copy()

# KPI tiles
col1, col2, col3 = st.columns(3)
col1.metric("Cities monitored", f"{filtered['city'].nunique():,}")
# high risk count
risk = filtered[filtered["aqi"] >= 151].shape[0]
col2.metric("Unhealthy or worse", f"{risk:,}")
col3.metric("Latest timestamp (AWST)", filtered["observed_at_awst"].max().strftime("%Y-%m-%d %H:%M"))

# Map
st.subheader("Map: City AQI (bubble sized by AQI; colored by category)")
fig_map = px.scatter_mapbox(
    filtered,
    lat="lat", lon="lon", color="aqi_category", size="aqi",
    hover_data=["city","aqi","aqi_category","dominentpol","observed_at_awst"],
    zoom=3, height=500
)
fig_map.update_layout(mapbox_style="open-street-map", margin=dict(l=0,r=0,t=0,b=0))
st.plotly_chart(fig_map, use_container_width=True)

# Bar chart by city
st.subheader("AQI by city")
fig_bar = px.bar(filtered.sort_values("aqi", ascending=False), x="city", y="aqi", color="aqi_category")
fig_bar.update_layout(xaxis_title="", yaxis_title="AQI")
st.plotly_chart(fig_bar, use_container_width=True)

# Time series (if we have a local log)
if df_log is not None:
    st.subheader("Trend: AQI over time (local log)")
    df_log = df_log[df_log["city"].isin(pick_cities)].copy()
    if not df_log.empty:
        df_log["observed_at_awst"] = df_log["observed_at_utc"].dt.tz_convert("Australia/Perth")
        fig_ts = px.line(df_log.sort_values("observed_at_awst"), x="observed_at_awst", y="aqi", color="city")
        fig_ts.update_layout(xaxis_title="Time (AWST)", yaxis_title="AQI")
        st.plotly_chart(fig_ts, use_container_width=True)
    else:
        st.info("No log yet—run the fetcher a few times to build history.")

# Pollutant detail table
if pick_pol:
    st.subheader(f"{pick_pol.upper()} concentration snapshot")
    cols = ["city","aqi","aqi_category","dominentpol","observed_at_awst", pick_pol]
    st.dataframe(filtered[cols].sort_values(pick_pol, ascending=False), use_container_width=True)

st.download_button("Download snapshot (CSV)", filtered.to_csv(index=False).encode("utf-8"), "aqi_snapshot.csv")
