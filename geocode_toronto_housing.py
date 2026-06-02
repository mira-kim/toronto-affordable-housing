"""
Toronto Affordable Housing Geocoder
------------------------------------
Fetches subsidized housing listings from Toronto Open Data (CKAN),
geocodes addresses using ArcGIS (free, no API key), and saves a
cached CSV with lat/lon ready for mapping.

Run once. Re-running skips already-geocoded rows.

Usage:
    pip install requests pandas geopy
    python geocode_toronto_housing.py
"""

import os

import pandas as pd
import requests
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import ArcGIS, Nominatim

from config import CKAN_BASE, DATA_DIR, GEOCODE_SUFFIX

DATASETS = {
    "subsidized_buildings": {
        "resource_id": "449a5cf0-af7d-43cc-bff9-4330008f1bd4",
        "address_field": "Building Address",
        "name_field": "Building Complex Name",
        "native_lat": "Latitude",   # dataset already includes coordinates
        "native_lon": "Longitude",
        "output_file": "subsidized_buildings_geocoded.csv",
    },
    "subsidized_units": {
        "resource_id": "feef5b9e-06f6-4f25-ab4a-8d7a1176c555",
        "address_field": None,   # unit-level detail, joined to buildings
        "name_field": None,
        "native_lat": None,
        "native_lon": None,
        "output_file": "subsidized_units.csv",
    },
}

DATA_DIR = "data"


# ── Geocoders ─────────────────────────────────────────────────────────────────

def _build_geocoders() -> list[tuple[str, object]]:
    arcgis    = ArcGIS(timeout=10)
    nominatim = Nominatim(user_agent="toronto_affordable_housing_mapper", timeout=10)
    arcgis_rate = RateLimiter(arcgis.geocode,    min_delay_seconds=0.1)
    nom_rate    = RateLimiter(nominatim.geocode,  min_delay_seconds=1.1)
    return [("arcgis", arcgis_rate), ("nominatim", nom_rate)]


def geocode(address: str, geocoders: list[tuple[str, object]]) -> tuple[float | None, float | None, str]:
    """
    Try each geocoder in order, return first hit.
    Returns (lat, lon, source) where source is 'arcgis', 'nominatim', or 'failed'.
    """
    full = f"{address}, {GEOCODE_SUFFIX}"
    for label, fn in geocoders:
        try:
            loc = fn(full)
            if loc:
                return round(loc.latitude, 6), round(loc.longitude, 6), label
        except Exception as e:
            print(f"  {label} error for '{address}': {e}")
    return None, None, "failed"


# ── CKAN Fetcher ──────────────────────────────────────────────────────────────

def fetch_all_records(resource_id: str) -> list[dict]:
    """
    Pages through CKAN datastore_search to get all records.
    CKAN's default limit is 100; we use 1000 per page.
    """
    records = []
    offset  = 0
    limit   = 1000

    while True:
        resp = requests.get(
            f"{CKAN_BASE}/datastore_search",
            params={"resource_id": resource_id, "limit": limit, "offset": offset},
            timeout=30,
        )
        resp.raise_for_status()
        data  = resp.json()
        batch = data["result"]["records"]

        if not batch:
            break

        records.extend(batch)
        total = data["result"]["total"]
        offset += limit
        print(f"  Fetched {len(records)}/{total} records...")

        if len(records) >= total or offset > total + limit:
            break

    return records


# ── Geocoding pipeline ────────────────────────────────────────────────────────

def _geocode_dataframe(
    df: pd.DataFrame,
    addr_col: str,
    out_path: str,
    geocoders: list[tuple[str, object]],
) -> pd.DataFrame:
    """Geocode rows missing lat/lon, checkpointing every 25 rows."""
    clean_addr = df[addr_col].astype(str).str.strip()
    to_geocode = df[
        df["lat"].isna()
        & df[addr_col].notna()
        & (clean_addr != "")
        & (clean_addr.str.lower() != "nan")
    ]
    total_todo = len(to_geocode)
    print(f"  Addresses to geocode: {total_todo}")

    for i, (idx, row) in enumerate(to_geocode.iterrows()):
        address = str(row[addr_col]).strip()
        print(f"  [{i+1}/{total_todo}] {address}")
        lat, lon, source = geocode(address, geocoders)

        df.at[idx, "lat"]            = lat
        df.at[idx, "lon"]            = lon
        df.at[idx, "geocode_source"] = source

        if source == "failed":
            print(f"    FAILED: {address}")
        else:
            print(f"    {source}: {lat}, {lon}")

        if (i + 1) % 25 == 0:
            df.to_csv(out_path, index=False)
            print("  [checkpoint saved]")

    return df


def _print_summary(df: pd.DataFrame, addr_col: str, out_path: str) -> None:
    total       = len(df)
    success     = df["lat"].notna().sum()
    failed      = df["lat"].isna().sum()
    arcgis_hits = (df["geocode_source"] == "arcgis").sum()
    nom_hits    = (df["geocode_source"] == "nominatim").sum()

    print("\n  Results:")
    print(f"    Total addresses : {total}")
    print(f"    Geocoded        : {success} ({100 * success // (total or 1)}%)")
    print(f"      via ArcGIS    : {arcgis_hits}")
    print(f"      via Nominatim : {nom_hits}")
    print(f"    Failed          : {failed}")
    print(f"  Saved to: {out_path}")

    if failed > 0:
        print("\n  Failed addresses (review manually):")
        for addr in df[df["lat"].isna()][addr_col].tolist():
            print(f"    - {addr}")


# ── Main Pipeline ─────────────────────────────────────────────────────────────

def run():
    os.makedirs(DATA_DIR, exist_ok=True)
    geocoders = _build_geocoders()

    for name, cfg in DATASETS.items():
        print(f"\n{'='*60}")
        print(f"Dataset: {name}")
        print(f"{'='*60}")

        out_path = os.path.join(DATA_DIR, cfg["output_file"])

        print("Fetching records from CKAN...")
        records = fetch_all_records(cfg["resource_id"])
        df = pd.DataFrame(records)
        print(f"  Total records: {len(df)}")
        print(f"  Columns: {list(df.columns)}")

        if cfg["address_field"] is None:
            df.to_csv(out_path, index=False)
            print(f"  Saved (no geocoding needed): {out_path}")
            continue

        addr_col = cfg["address_field"]

        if os.path.exists(out_path):
            existing = pd.read_csv(out_path)
            print(f"  Resuming — {existing['lat'].notna().sum()} addresses already geocoded")
            df = pd.merge(
                df,
                existing[["_id", "lat", "lon", "geocode_source"]],
                on="_id",
                how="left",
            )
        else:
            df["lat"]            = None
            df["lon"]            = None
            df["geocode_source"] = None

            # Seed from coordinates the dataset already provides
            native_lat = cfg.get("native_lat")
            native_lon = cfg.get("native_lon")
            if native_lat and native_lon and native_lat in df.columns:
                has_coords = df[native_lat].notna() & df[native_lon].notna()
                df.loc[has_coords, "lat"]            = df.loc[has_coords, native_lat]
                df.loc[has_coords, "lon"]            = df.loc[has_coords, native_lon]
                df.loc[has_coords, "geocode_source"] = "dataset"
                print(f"  Seeded {has_coords.sum()} coordinates from dataset")

        df = _geocode_dataframe(df, addr_col, out_path, geocoders)
        df.to_csv(out_path, index=False)
        _print_summary(df, addr_col, out_path)


if __name__ == "__main__":
    run()
