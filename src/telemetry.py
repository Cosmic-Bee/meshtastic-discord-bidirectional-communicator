import csv
import asyncio
import requests
from datetime import datetime, timezone
from config import FIRMS_MAP_KEY

async def fetch_firms_data(lat, lon):
    if not FIRMS_MAP_KEY:
        return []
    try:
        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_MAP_KEY}/VIIRS_SNPP_NRT/{lon-0.5},{lat-0.5},{lon+0.5},{lat+0.5}/1"
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, lambda: requests.get(url, timeout=10))
        if res.status_code != 200:
            return []
            
        reader = csv.DictReader(res.text.strip().split('\n'))
        alerts = []
        for row in reader:
            if row.get('confidence') in ['h', 'n']:
                alerts.append({
                    "payload": {"areaDesc": "Proximity Wildfire Detect", "event": "Thermal Anomaly", "instruction": "Evacuate if smoke/fire approaches", "severity": "Extreme"},
                    "severity": "critical",
                    "type": "fire",
                    "id": f"firms_{row.get('latitude')}_{row.get('longitude')}_{row.get('acq_time')}"
                })
        return alerts
    except Exception as e:
        print(f"⚠️ FIRMS error: {e}")
        return []

async def fetch_earthquake_data(lat, lon):
    try:
        today_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        url = f"https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&latitude={lat}&longitude={lon}&maxradiuskm=200&starttime={today_date}"
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, lambda: requests.get(url, timeout=10))
        if res.status_code != 200:
            return []
            
        data = res.json()
        alerts = []
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            if props.get("mag", 0) >= 3.5:
                alerts.append({
                    "payload": {"areaDesc": props.get("place", "Nearby"), "event": "Earthquake Detected", "instruction": "Drop, Cover, and Hold On", "severity": "Severe"},
                    "severity": "critical",
                    "type": "earthquake",
                    "id": f"usgs_{feature.get('id')}"
                })
        return alerts
    except Exception as e:
        print(f"⚠️ USGS error: {e}")
        return []

async def fetch_weather_alerts(lat, lon):
    try:
        url = f"https://api.weather.gov/alerts/active?point={lat},{lon}"
        headers = {"User-Agent": "EmergencyCommsMeshBridge/1.0"}
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, lambda: requests.get(url, headers=headers, timeout=10))
        if res.status_code != 200:
            return []
            
        data = res.json()
        alerts = []
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            if props.get("severity") in ["Severe", "Extreme"]:
                alerts.append({
                    "payload": {"areaDesc": props.get("areaDesc", "Local Region"), "event": props.get("event"), "instruction": props.get("instruction", "Take cover"), "severity": props.get("severity")},
                    "severity": "critical" if props.get("severity") == "Extreme" else "warning",
                    "type": "weather",
                    "id": props.get("id")
                })
        return alerts
    except Exception as e:
        print(f"⚠️ NWS error: {e}")
        return []

async def check_emergency_apis(lat, lon):
    # --- Demonstration lat/long ---
    if lat == 99.99 and lon == 99.99:
        return [{
            "payload": {
                "areaDesc": "Contest Demo Zone", 
                "event": "Simulated Class 5 Wildfire", 
                "instruction": "Immediate evacuation required. Deploy water reserves.", 
                "severity": "Extreme"
            },
            "severity": "critical",
            "type": "fire",
            "id": "demo_fire_001"
        }]

    firms, quake, weather = await asyncio.gather(
        fetch_firms_data(lat, lon),
        fetch_earthquake_data(lat, lon),
        fetch_weather_alerts(lat, lon)
    )
    return firms + quake + weather
