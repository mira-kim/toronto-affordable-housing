"""
Preview the map with mock TCHC listing data — no server needed.

Reads the generated map HTML, injects a fetch() override that returns
mock data, writes data/toronto_housing_map_preview.html, and opens it
in your default browser.

Usage:
    python preview_listings.py          # active listings (default)
    python preview_listings.py empty    # no listings / empty state
"""

import json
import os
import sys
import webbrowser

MAP_SRC     = os.path.join("data", "toronto_housing_map.html")
MAP_PREVIEW = os.path.join("data", "toronto_housing_map_preview.html")

MOCK_ACTIVE = {
    "has_listings": True,
    "listings": [
        {
            "title": "Affordable housing rental units at 1070 Eastern Ave. (Don Summerville)",
            "address": "1070 Eastern Ave",
            "units": [
                {"count": 16, "type": "1BR"},
                {"count": 13, "type": "2BR"},
                {"count": 6,  "type": "3BR"},
            ],
            "eoi": "Opens January 21, 2026 — closes February 20, 2026",
            "details": [],
        },
        {
            "title": "Affordable housing rental units at 5 Strachan Ave",
            "address": "5 Strachan Ave",
            "units": [
                {"count": 8, "type": "1BR"},
                {"count": 4, "type": "2BR"},
            ],
            "eoi": "Opens March 3, 2026 — closes March 31, 2026",
            "details": [],
        },
    ],
    "summary": "1070 Eastern Ave",
    "last_checked": "2026-05-29T10:00:00",
    "last_changed": "2026-05-29T09:45:00",
}

MOCK_EMPTY = {
    "has_listings": False,
    "listings": [],
    "summary": "",
    "last_checked": "2026-05-29T10:00:00",
    "last_changed": None,
}

MOCK_SCRIPT = """
<script>
// ── Preview override: mock /api/listings (no server needed) ──────────────────
(function () {
  const _realFetch = window.fetch;
  window.fetch = function (url, opts) {
    if (typeof url === 'string' && url.includes('/api/listings')) {
      const mockData = __MOCK_DATA__;
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockData),
      });
    }
    return _realFetch.apply(this, arguments);
  };
})();
</script>
"""


def main():
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "active"

    if not os.path.exists(MAP_SRC):
        print(f"Map not found at {MAP_SRC}. Run map_toronto_housing.py first.")
        return

    mock_data = MOCK_EMPTY if mode == "empty" else MOCK_ACTIVE
    label     = "empty (no listings)" if mode == "empty" else "active (2 listings)"

    with open(MAP_SRC, encoding="utf-8") as f:
        html = f.read()

    mock_json = json.dumps(mock_data, indent=2)
    script    = MOCK_SCRIPT.replace("__MOCK_DATA__", mock_json)
    patched   = html.replace("</head>", script + "\n</head>", 1)

    with open(MAP_PREVIEW, "w", encoding="utf-8") as f:
        f.write(patched)

    preview_path = os.path.abspath(MAP_PREVIEW)
    print(f"Preview mode : {label}")
    print(f"Written to   : {preview_path}")
    print("Opening in browser...")
    webbrowser.open(f"file:///{preview_path.replace(os.sep, '/')}")


if __name__ == "__main__":
    main()
