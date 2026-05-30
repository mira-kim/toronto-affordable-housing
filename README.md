# Toronto Affordable Housing Map

An interactive map of Toronto's subsidized and affordable housing buildings, with live monitoring for new TCHC unit listings and email alerts.

## What it does

- **Maps 578 subsidized housing buildings** across Toronto using data from the [Toronto Open Data](https://open.toronto.ca/) CKAN API
- **Filters** by bedroom size, provider, building type, ward, accessibility features, amenities, and building mandate
- **Shows waitlist stats** (city-wide RGI waitlist size, updated each quarter)
- **Monitors TCHC** — scrapes [torontohousing.ca](https://torontohousing.ca/prospective-tenants/affordable-rent) every 6 hours for new affordable rent listings
- **Highlights available buildings** on the map when TCHC units are posted, re-checking every 10 minutes while the tab is open
- **Email alerts** — subscribers are notified when new TCHC listings appear or change

## Files

| File | Purpose |
|------|---------|
| `config.py` | Shared constants (TCHC URL) used across modules |
| `geocode_toronto_housing.py` | Fetches building data from Toronto Open Data and geocodes addresses. Run once to produce the CSV. |
| `map_toronto_housing.py` | Reads the geocoded CSV and generates `data/toronto_housing_map.html` from `map_template.html` |
| `map_template.html` | HTML/CSS/JS template for the interactive map — edit this to change the map UI |
| `monitor_tchc.py` | Scrapes torontohousing.ca for new listings; handles state, change detection, and email notifications |
| `server.py` | Flask server — serves the map, exposes `/api/listings` and `/api/subscribe`, polls TCHC every 6 hours |
| `preview_listings.py` | Dev tool — opens a browser preview of the map with mock listing data (no server needed) |
| `tests/test_monitor_tchc.py` | Unit tests for scraper parsing, state extraction, subscriber validation, and email config |
| `tests/test_server.py` | Unit tests for email regex, rate limiter, and API endpoints |

## Setup

**Install dependencies:**
```
pip install flask requests beautifulsoup4 pandas geopy
```

**Geocode buildings** (run once — takes a few minutes):
```
python geocode_toronto_housing.py
```

**Generate the map:**
```
python map_toronto_housing.py
```

**Start the server:**
```
python server.py
```

Then open [http://localhost:5001](http://localhost:5001).

## Email alerts

Credentials are read from environment variables first, falling back to a JSON config file.

**Option A — environment variables (recommended):**
```
set GMAIL_USER=you@gmail.com
set GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

**Option B — config file:**
1. Enable 2-Step Verification on your Gmail account
2. Generate an [App Password](https://myaccount.google.com/apppasswords)
3. Create `data/email_config.json`:
```json
{ "gmail_user": "you@gmail.com", "gmail_app_password": "xxxx xxxx xxxx xxxx" }
```

Subscribers are stored in `data/subscribers.json`. Anyone who enters their email in the map UI is added automatically.

## Data sources

- **Buildings:** [Toronto Open Data — Subsidized Housing](https://open.toronto.ca/dataset/affordable-housing/) (CKAN API)
- **Waitlist:** Toronto Open Data quarterly RGI waitlist statistics
- **TCHC listings:** [torontohousing.ca/prospective-tenants/affordable-rent](https://torontohousing.ca/prospective-tenants/affordable-rent) (scraped)

## Development

**Preview the map with mock listings** (no server required):
```
python preview_listings.py          # active state — shows 2 mock listings
python preview_listings.py empty    # empty state — shows "no units available"
```

**Run tests:**
```
pip install pytest
pytest tests/ -v
```

**Lint:**
```
pip install ruff
ruff check .
```
