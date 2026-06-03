"""
Toronto Affordable Housing Map
--------------------------------
Reads the geocoded CSV produced by scripts/geocode_toronto_housing.py,
fetches live data from all registered data sources, and renders an
interactive Leaflet map as a standalone HTML file.

Usage (from project root):
    python scripts/map_toronto_housing.py
"""

import json
import os
import sys

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from config import (
    APPLY_URL, COHB_URL, DATA_DIR, MAP_FILE,
    TCHC_URL as TCHC_AFFORDABLE_URL,
)
import data_sources

INPUT_FILE = os.path.join(DATA_DIR, "subsidized_buildings_geocoded.csv")

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
    with open(os.path.join(_ROOT, "map_template.html"), encoding="utf-8") as f:
        return f.read()


def build_html(buildings: list[dict], data: dict) -> str:
    options       = get_filter_options(buildings)
    waitlist      = data.get("waitlist")
    units_by_bldg = data.get("units_by_building", {})

    html = _load_template()
    html = html.replace("__BUILDINGS__",         json.dumps(buildings,       ensure_ascii=False))
    html = html.replace("__WAITLIST__",          json.dumps(waitlist,        ensure_ascii=False) if waitlist else "null")
    html = html.replace("__OPTIONS__",           json.dumps(options,         ensure_ascii=False))
    html = html.replace("__UNITS_BY_BUILDING__", json.dumps(units_by_bldg,  ensure_ascii=False))
    html = html.replace("__APPLY_URL__",           json.dumps(APPLY_URL,           ensure_ascii=False))
    html = html.replace("__COHB_URL__",            json.dumps(COHB_URL,            ensure_ascii=False))
    html = html.replace("__TCHC_AFFORDABLE_URL__", json.dumps(TCHC_AFFORDABLE_URL, ensure_ascii=False))
    return html


# ── Entry point ───────────────────────────────────────────────────────────────

def run():
    if not os.path.exists(INPUT_FILE):
        print(f"No data found at {INPUT_FILE}")
        print("Run scripts/geocode_toronto_housing.py first.")
        return

    df = pd.read_csv(INPUT_FILE)
    print(f"Loaded {len(df)} buildings")

    print("Fetching external data sources...")
    data = data_sources.fetch_all()

    buildings = prepare_buildings(df)
    html = build_html(buildings, data)

    with open(MAP_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Saved: {MAP_FILE}")


if __name__ == "__main__":
    run()
