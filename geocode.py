from pathlib import Path
import json
import math
import os
import time

import pandas as pd
#python library for calling web apis 
import requests

base_dir = Path(__file__).resolve().parent

file_path = base_dir / "Point 1 data.csv"
output_path = base_dir / "Point 1 data geocoded.csv"
cache_path = base_dir / "geocode_cache.json"

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")

# The addresses in the data are short (like "Oluawo") so add the area to help Google find them
AREA_SUFFIX = ", Ona Ara, Oyo State, Nigeria"


def build_address(row):
    for col in ["Full Address Single-Family Dwelling", "Small Mfd Address", "High Rise Address"]:
        if pd.notna(row[col]) and str(row[col]).strip():
            return str(row[col]).strip()
    return None


def geocode(address):
    params = {
        "address": address + AREA_SUFFIX,
        "components": "country:NG",
        "key": API_KEY,
    }
    response = requests.get(GEOCODE_URL, params=params, timeout=10)
    data = response.json()

    if data["status"] == "OK":
        location = data["results"][0]["geometry"]["location"]
        return [location["lat"], location["lng"]]
    if data["status"] == "ZERO_RESULTS":
        return None
    raise RuntimeError(f"Geocoding failed for {address!r}: {data['status']} {data.get('error_message', '')}")


def haversine_km(lat1, lon1, lat2, lon2):
    """Straight-line distance in km between two coordinates."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def main():
    if not API_KEY:
        raise SystemExit("Set the GOOGLE_MAPS_API_KEY environment variable first.")

    df = pd.read_csv(file_path, low_memory=False)
    df["Address"] = df.apply(build_address, axis=1)

    # Cache results so each unique address is only paid for once, even across reruns
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

    unique_addresses = df["Address"].dropna().unique()
    to_fetch = [a for a in unique_addresses if a not in cache]
    print(f"{len(unique_addresses)} unique addresses, {len(to_fetch)} need geocoding")

    for i, address in enumerate(to_fetch, 1):
        cache[address] = geocode(address)
        if i % 50 == 0:
            cache_path.write_text(json.dumps(cache, indent=2))
            print(f"  {i}/{len(to_fetch)}")
        time.sleep(0.05)
    cache_path.write_text(json.dumps(cache, indent=2))

    coords = df["Address"].map(lambda a: cache.get(a) if a else None)
    df["Latitude"] = coords.map(lambda c: c[0] if c else None)
    df["Longitude"] = coords.map(lambda c: c[1] if c else None)
    df["Coordinates"] = coords.map(lambda c: f"{c[0]}, {c[1]}" if c else None)

    df.to_csv(output_path, index=False)
    print(f"Geocoded {df['Coordinates'].notna().sum()} of {len(df)} rows -> {output_path.name}")


if __name__ == "__main__":
    main()
