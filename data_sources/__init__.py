from . import ckan_waitlist, ckan_units

SOURCES = [ckan_waitlist, ckan_units]


def fetch_all() -> dict:
    out = {}
    for source in SOURCES:
        try:
            out.update(source.fetch())
        except Exception as e:
            print(f"  data_sources: {source.__name__} failed — {e}")
    return out
