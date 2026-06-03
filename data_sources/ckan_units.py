import requests
from config import CKAN_BASE

RESOURCE_ID = "feef5b9e-06f6-4f25-ab4a-8d7a1176c555"


def fetch() -> dict:
    records, offset = [], 0
    while True:
        resp = requests.get(
            f"{CKAN_BASE}/datastore_search",
            params={"resource_id": RESOURCE_ID, "limit": 1000, "offset": offset},
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json()["result"]
        batch  = result["records"]
        if not batch:
            break
        records.extend(batch)
        if len(records) >= result["total"]:
            break
        offset += 1000

    by_building: dict[str, list[dict]] = {}
    for r in records:
        name = (r.get("Building Complex Name") or "").strip()
        if not name:
            continue
        by_building.setdefault(name, []).append({
            "unit_size":          r.get("Unit Size"),
            "income_limit":       r.get("Household Income Limit"),
            "available_last_12m": r.get("Units Available in the Last 12 Months"),
            "subsidized_units":   r.get("Number of Subsidized Units"),
            "market_units":       r.get("Number of Market Rent Units"),
            "mandate":            r.get("Mandate Description"),
        })

    print(f"  ckan_units: {len(by_building)} buildings, {len(records)} unit rows")
    return {"units_by_building": by_building}
