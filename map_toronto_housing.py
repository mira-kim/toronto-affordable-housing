"""
Toronto Affordable Housing Map
--------------------------------
Reads the geocoded CSV produced by geocode_toronto_housing.py and
renders an interactive Leaflet map as a standalone HTML file.

Usage:
    pip install pandas requests
    python map_toronto_housing.py
"""

import os
import json
import requests
import pandas as pd

from config import (
    APPLY_URL, CKAN_BASE, CKAN_WAITLIST_RESOURCE, COHB_URL,
    DATA_DIR, MAP_FILE, TCHC_URL as TCHC_AFFORDABLE_URL,
)

INPUT_FILE  = os.path.join(DATA_DIR, "subsidized_buildings_geocoded.csv")
OUTPUT_FILE = MAP_FILE

WARD_NAMES = {
    "1":"Etobicoke North","2":"Etobicoke Centre","3":"Etobicoke–Lakeshore",
    "4":"Parkdale–High Park","5":"York South–Weston","6":"York Centre",
    "7":"Humber River–Black Creek","8":"Eglinton–Lawrence","9":"Davenport",
    "10":"Spadina–Fort York","11":"University–Rosedale","12":"Toronto–St. Paul's",
    "13":"Toronto Centre","14":"Toronto–Danforth","15":"Don Valley West",
    "16":"Don Valley East","17":"Don Valley North","18":"Willowdale",
    "19":"Beaches–East York","20":"Scarborough Southwest","21":"Scarborough Centre",
    "22":"Scarborough–Agincourt","23":"Scarborough North","24":"Scarborough–Guildwood",
    "25":"Scarborough–Rouge Park",
}


# ── Data prep ─────────────────────────────────────────────────────────────────

def fetch_waitlist_stats() -> dict | None:
    try:
        resp = requests.get(
            f"{CKAN_BASE}/datastore_search",
            params={"resource_id": CKAN_WAITLIST_RESOURCE, "limit": 100},
            timeout=15,
        )
        resp.raise_for_status()
        records = resp.json()["result"]["records"]
        if not records:
            return None
        return {"latest": records[-1], "previous": records[-2] if len(records) >= 2 else None}
    except Exception as e:
        print(f"  Could not fetch waitlist stats: {e}")
        return None


def prepare_buildings(df: pd.DataFrame) -> list[dict]:
    df = df.where(pd.notna(df), None)
    df["Ward"] = df["Ward"].apply(lambda v: str(int(v)) if v is not None else None)
    return df.to_dict(orient="records")


def get_filter_options(buildings: list[dict]) -> dict:
    wards = sorted(
        {b["Ward"] for b in buildings if b.get("Ward")},
        key=int,
    )
    mandates = sorted({
        str(b.get("Building Mandate1") or "").strip()
        for b in buildings
        if str(b.get("Building Mandate1") or "").strip()
    })
    provider_types = sorted({b.get("Provider Type") for b in buildings if b.get("Provider Type")})
    btypes: set[str] = set()
    for b in buildings:
        for t in str(b.get("Building Type") or "").split("|"):
            if t.strip():
                btypes.add(t.strip())
    return {
        "wards":         wards,
        "wardNames":     WARD_NAMES,
        "mandates":      mandates,
        "providerTypes": provider_types,
        "buildingTypes": sorted(btypes),
    }


# ── HTML generation ───────────────────────────────────────────────────────────

def _load_template() -> str:
    with open(os.path.join(_HERE, "map_template.html"), encoding="utf-8") as f:
        return f.read()


def build_html(buildings: list[dict], waitlist: dict | None) -> str:
    options = get_filter_options(buildings)
    html = _load_template()
    html = html.replace("__BUILDINGS__",  json.dumps(buildings,  ensure_ascii=False))
    html = html.replace("__WAITLIST__",   json.dumps(waitlist,   ensure_ascii=False) if waitlist else "null")
    html = html.replace("__OPTIONS__",    json.dumps(options,    ensure_ascii=False))
    html = html.replace("__APPLY_URL__",           json.dumps(APPLY_URL,           ensure_ascii=False))
    html = html.replace("__COHB_URL__",            json.dumps(COHB_URL,            ensure_ascii=False))
    html = html.replace("__TCHC_AFFORDABLE_URL__", json.dumps(TCHC_AFFORDABLE_URL, ensure_ascii=False))
    return html


# ── Entry point ───────────────────────────────────────────────────────────────

def run():
    if not os.path.exists(INPUT_FILE):
        print(f"No data found at {INPUT_FILE}")
        print("Run geocode_toronto_housing.py first.")
        return

    df = pd.read_csv(INPUT_FILE)
    print(f"Loaded {len(df)} records")

    print("Fetching waitlist stats...")
    waitlist = fetch_waitlist_stats()
    if waitlist:
        print(f"  Latest quarter: {waitlist['latest'].get('Quarter', '?')}")

    buildings = prepare_buildings(df)
    html = build_html(buildings, waitlist)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved: {OUTPUT_FILE}")
    print("Open in a browser to explore.")




if __name__ == "__main__":
    run()
