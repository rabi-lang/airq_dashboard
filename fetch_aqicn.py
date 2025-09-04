import os, time, json, pathlib, requests
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("WAQI_TOKEN")
assert TOKEN, "Missing WAQI_TOKEN in .env"

# Parse city list from .env (fallback to Perth only)
def parse_cities(env_str: str | None):
    if not env_str:
        return {"Perth": (-31.95, 115.86)}
    out = {}
    for item in env_str.split(";"):
        if not item.strip(): continue
        name, coords = item.split(":")
        lat, lon = map(float, coords.split(","))
        out[name.strip()] = (lat, lon)
    return out

CITIES = parse_cities(os.getenv("CITIES"))
BASE = "https://api.waqi.info/feed"

def aqi_band(aqi: int | float | None):
    if aqi is None or pd.isna(aqi): return ("Unknown", "n/a")
    aqi = float(aqi)
    if   aqi <=  50: return ("Good", "0-50")
    elif aqi <= 100: return ("Moderate", "51-100")
    elif aqi <= 150: return ("Unhealthy for Sensitive Groups", "101-150")
    elif aqi <= 200: return ("Unhealthy", "151-200")
    elif aqi <= 300: return ("Very Unhealthy", "201-300")
    else:            return ("Hazardous", "300+")  # AQICN category ranges
# Category ranges documented on the API page. :contentReference[oaicite:3]{index=3}

def fetch_geo(lat: float, lon: float, token: str):
    url = f"{BASE}/geo:{lat};{lon}/?token={token}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json(), url

def normalize_record(j: dict, city_label: str):
    """Map WAQI JSON into one tidy row."""
    if j.get("status") != "ok": 
        return None
    d = j["data"]
    # pollutants live under "iaqi": e.g., {"pm25":{"v":21}, "pm10":{"v":37}, ...}
    iaqi = d.get("iaqi", {}) or {}
    p = {k: v.get("v") for k, v in iaqi.items() if isinstance(v, dict)}
    # time: d["time"]["s"] like "2025-09-04 11:00:00", d["time"]["tz"] like "+08:00"
    t = d.get("time", {}) or {}
    ts = t.get("s")
    # Pandas can parse the offset in the string if present; otherwise treat as naive UTC.
    observed = pd.to_datetime(ts, utc=True, errors="coerce")
    lat, lon = None, None
    cinfo = d.get("city", {}) or {}
    if "geo" in cinfo and isinstance(cinfo["geo"], (list, tuple)) and len(cinfo["geo"]) == 2:
        lat, lon = cinfo["geo"]
    row = {
        "city": city_label or cinfo.get("name"),
        "aqi": d.get("aqi"),
        "observed_at_utc": observed,
        "lat": lat, "lon": lon,
        "station_name": cinfo.get("name"),
        "dominentpol": d.get("dominentpol")
    }
    # flatten pollutants
    for key in ["pm25","pm10","o3","no2","so2","co","nh3"]:
        row[key] = p.get(key)
    # category
    cat, range_ = aqi_band(row["aqi"])
    row["aqi_category"] = cat
    row["aqi_range"] = range_
    return row

def main():
    records = []
    urls = []
    for name, (lat, lon) in CITIES.items():
        try:
            js, url = fetch_geo(lat, lon, TOKEN)
            urls.append(url)
            rec = normalize_record(js, name)
            if rec:
                # If API city geo missing, ensure coords from config
                rec["lat"] = rec["lat"] if pd.notna(rec["lat"]) else lat
                rec["lon"] = rec["lon"] if pd.notna(rec["lon"]) else lon
                records.append(rec)
            time.sleep(0.3)  # be polite
        except Exception as e:
            print(f"[warn] {name}: {e}")
    df = pd.DataFrame.from_records(records)
    pathlib.Path("data").mkdir(parents=True, exist_ok=True)
    # Cache latest snapshot
    latest = "data/aqi_latest.csv"
    df.to_csv(latest, index=False)
    print(f"Saved {len(df)} rows → {latest}")
    # Append to log (local only; respect AQICN data usage terms)
    logp = pathlib.Path("data/aqi_log.csv")
    if logp.exists():
        old = pd.read_csv(logp, parse_dates=["observed_at_utc"])
        cat_cols = ["aqi_category","aqi_range","dominentpol"]
        df_cat = df.copy()
        df_cat[cat_cols] = df_cat[cat_cols].astype(str)
        all_rows = pd.concat([old, df_cat], ignore_index=True)
        # dedupe by city + timestamp
        all_rows = all_rows.drop_duplicates(subset=["city","observed_at_utc"])
        all_rows.to_csv(logp, index=False)
    else:
        df.to_csv(logp, index=False)
    print(f"Log updated → {logp}")
    # Save provenance (endpoints hit)
    with open("data/last_urls.txt","w",encoding="utf-8") as f:
        f.write("\n".join(urls))

if __name__ == "__main__":
    main()
