import requests
from config import CKAN_BASE, CKAN_WAITLIST_RESOURCE


def fetch() -> dict:
    resp = requests.get(
        f"{CKAN_BASE}/datastore_search",
        params={"resource_id": CKAN_WAITLIST_RESOURCE, "limit": 100},
        timeout=15,
    )
    resp.raise_for_status()
    records = resp.json()["result"]["records"]
    if not records:
        print("  ckan_waitlist: no records")
        return {"waitlist": None}
    waitlist = {
        "latest":   records[-1],
        "previous": records[-2] if len(records) >= 2 else None,
    }
    print(f"  ckan_waitlist: latest quarter {waitlist['latest'].get('Quarter', '?')}")
    return {"waitlist": waitlist}
