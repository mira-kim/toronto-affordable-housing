"""
TCHC Affordable Rent Monitor
Scrapes torontohousing.ca for new listings and notifies subscribers by email.

Setup email notifications (pick one):
  Option A — environment variables (recommended):
    set GMAIL_USER=you@gmail.com
    set GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

  Option B — config file:
  1. Enable 2-Step Verification on your Gmail account
  2. Go to myaccount.google.com/apppasswords and generate an App Password
  3. Create data/email_config.json:
     { "gmail_user": "you@gmail.com", "gmail_app_password": "xxxx xxxx xxxx xxxx" }

Run standalone:
  python monitor_tchc.py
"""

import hashlib
import json
import os
import re
import smtplib
from datetime import datetime
from email.mime.text import MIMEText

import requests
from bs4 import BeautifulSoup

from config import TCHC_URL

STATE_FILE       = "data/tchc_state.json"
SUBSCRIBERS_FILE = "data/subscribers.json"
EMAIL_CONFIG     = "data/email_config.json"

NUMBER_WORDS = {
    "zero":0,"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,
    "eight":8,"nine":9,"ten":10,"eleven":11,"twelve":12,"thirteen":13,
    "fourteen":14,"fifteen":15,"sixteen":16,"seventeen":17,"eighteen":18,
    "nineteen":19,"twenty":20,"thirty":30,"forty":40,"fifty":50,
}


# ── Scraping ──────────────────────────────────────────────────────────────────

def fetch_page() -> str:
    resp = requests.get(
        TCHC_URL,
        timeout=15,
        headers={"User-Agent": "Mozilla/5.0 (toronto-housing-monitor/1.0)"},
    )
    resp.raise_for_status()
    return resp.text


def _parse_unit_count(text: str) -> int | None:
    """'Sixteen one-bedroom units' → 16"""
    t = text.lower().strip()
    for word, n in sorted(NUMBER_WORDS.items(), key=lambda x: -len(x[0])):
        if t.startswith(word):
            return n
    m = re.match(r"(\d+)", t)
    return int(m.group(1)) if m else None


def _parse_units(items: list[str]) -> list[dict]:
    """[' Sixteen one-bedroom units', ...] → [{count:16, type:'1BR'}, ...]"""
    TYPE_MAP = [
        ("bachelor", "Bachelor"), ("studio", "Studio"),
        ("one-bedroom", "1BR"),   ("1-bedroom", "1BR"),
        ("two-bedroom", "2BR"),   ("2-bedroom", "2BR"),
        ("three-bedroom", "3BR"), ("3-bedroom", "3BR"),
        ("four-bedroom", "4BR"),  ("4-bedroom", "4BR"),
        ("five-bedroom", "5BR"),  ("5-bedroom", "5BR"),
        ("six-bedroom",  "6BR"),  ("6-bedroom", "6BR"),
    ]
    units = []
    for item in items:
        count = _parse_unit_count(item)
        unit_type = next((label for key, label in TYPE_MAP if key in item.lower()), None)
        if count is not None and unit_type:
            units.append({"count": count, "type": unit_type})
    return units


def _extract_address(title: str) -> str:
    """'Affordable housing rental units at 1070 Eastern Ave. (Don Summerville)' → '1070 Eastern Ave'"""
    # Remove everything before "at " if present
    m = re.search(r"\bat\s+(.+)", title, re.IGNORECASE)
    s = m.group(1) if m else title
    # Strip trailing parenthetical, period, or known suffixes
    s = re.split(r"\s*\(|\.", s)[0]
    s = re.sub(r"\s*(affordable|housing|rental|units?)\s*$", "", s, flags=re.IGNORECASE)
    return s.strip()


def _extract_eoi(text: str) -> str:
    """Extract a concise EOI window string from a paragraph."""
    t = text.strip()
    # Try to find "open ... close ..." pattern with dates
    m = re.search(
        r"open\s+on\s+\w+,\s+(.+?),\s+and\s+close\s+on\s+\w+,\s+(.+?)(?:,\s+at\s+(.+?))?(?:\.|$)",
        t, re.IGNORECASE,
    )
    if m:
        return f"Opens {m.group(1)} — closes {m.group(2)}"
    # Fallback: truncate to 120 chars
    return t[:120] + ("…" if len(t) > 120 else "")


def parse_listings(html: str) -> list[dict]:
    """
    Extract structured listing data from the page.
    Returns a list of dicts with keys: title, address, units, eoi, details.
    """
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main")
    if not main:
        return []

    listings = []
    # Listings use <h4> tags; stop collecting at <h2>/<h3> section breaks
    for h4 in main.find_all("h4"):
        title = h4.get_text(strip=True)
        # Must contain a digit (street address number)
        if not any(c.isdigit() for c in title):
            continue

        listing: dict = {
            "title":   title,
            "address": _extract_address(title),
            "units":   [],
            "eoi":     "",
            "details": [],
        }

        el = h4.find_next_sibling()
        while el and el.name not in ("h2", "h3", "h4"):
            if el.name == "p":
                text = el.get_text(strip=True)
                if "expression of interest" in text.lower() or (
                    "open" in text.lower() and "close" in text.lower()
                ):
                    listing["eoi"] = _extract_eoi(text)
                elif text:
                    listing["details"].append(text)
            elif el.name in ("ul", "ol"):
                items = [li.get_text(strip=True) for li in el.find_all("li")]
                parsed = _parse_units(items)
                if parsed:
                    listing["units"].extend(parsed)
                else:
                    listing["details"].extend(items)
            el = el.find_next_sibling()

        if listing["units"] or listing["eoi"]:
            listings.append(listing)

    return listings


def _eoi_is_current(eoi: str) -> bool:
    """Return False if the EOI closing date is in the past."""
    if not eoi:
        return True
    m = re.search(r"closes\s+(\w+ \d+,\s*\d{4})", eoi, re.IGNORECASE)
    if not m:
        return True
    try:
        close_date = datetime.strptime(m.group(1).strip(), "%B %d, %Y").date()
        return close_date >= datetime.now().date()
    except ValueError:
        return True


def extract_state(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup.body
    if not main:
        return {"hash": "", "has_listings": False, "listings": [], "summary": ""}

    text      = main.get_text(separator="\n", strip=True)
    page_hash = hashlib.md5(text.encode()).hexdigest()
    listings  = [lst for lst in parse_listings(html) if _eoi_is_current(lst["eoi"])]
    has       = bool(listings)

    return {
        "hash":         page_hash,
        "has_listings": has,
        "listings":     listings,
        "summary":      listings[0]["address"] if listings else "",
    }


# ── State persistence ─────────────────────────────────────────────────────────

def load_state() -> dict:
    os.makedirs("data", exist_ok=True)
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "hash": None, "has_listings": False, "listings": [],
        "summary": "", "last_checked": None, "last_changed": None,
    }


def save_state(state: dict):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)


# ── Subscribers ───────────────────────────────────────────────────────────────

def load_subscribers() -> list[str]:
    if os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE) as f:
            return json.load(f).get("emails", [])
    return []


def add_subscriber(email: str) -> bool:
    if not email or "@" not in email:
        raise ValueError(f"Invalid email: {email!r}")
    os.makedirs("data", exist_ok=True)
    data = {"emails": []}
    if os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE) as f:
            data = json.load(f)
    if email in data["emails"]:
        return False
    data["emails"].append(email)
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    return True


# ── Email ─────────────────────────────────────────────────────────────────────

def _load_email_config() -> dict | None:
    """Read credentials from env vars first, fall back to JSON file."""
    user     = os.environ.get("GMAIL_USER")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if user and password:
        return {"gmail_user": user, "gmail_app_password": password}
    if os.path.exists(EMAIL_CONFIG):
        with open(EMAIL_CONFIG) as f:
            return json.load(f)
    return None


def send_notifications(listings: list[dict], subscribers: list[str]):
    if not subscribers:
        return

    cfg = _load_email_config()
    if not cfg:
        print(f"  No email credentials (set GMAIL_USER/GMAIL_APP_PASSWORD or create {EMAIL_CONFIG})")
        return

    subject = f"TCHC: New Affordable Units Available — {datetime.now().strftime('%b %d, %Y')}"

    lines = ["New listings on torontohousing.ca:\n"]
    for listing in listings:
        lines.append(f"  {listing['address']}")
        if listing["units"]:
            unit_str = "  · ".join(f"{u['count']}×{u['type']}" for u in listing["units"])
            lines.append(f"  Units: {unit_str}")
        if listing["eoi"]:
            lines.append(f"  {listing['eoi']}")
        lines.append("")
    lines.append(f"View and apply: {TCHC_URL}")
    body = "\n".join(lines)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(cfg["gmail_user"], cfg["gmail_app_password"])
            for email in subscribers:
                msg            = MIMEText(body)
                msg["Subject"] = subject
                msg["From"]    = cfg["gmail_user"]
                msg["To"]      = email
                smtp.sendmail(cfg["gmail_user"], email, msg.as_string())
                print(f"  Notified: {email}")
    except Exception as e:
        print(f"  Email error: {e}")


# ── Main check ────────────────────────────────────────────────────────────────

def check(notify: bool = True) -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Checking TCHC listings...")

    try:
        html    = fetch_page()
        current = extract_state(html)
        stored  = load_state()

        changed = current["hash"] != stored.get("hash")

        if changed:
            print(f"  Change detected — {len(current['listings'])} listing(s)")
            for listing in current["listings"]:
                units = "  ·  ".join(f"{u['count']}×{u['type']}" for u in listing["units"])
                print(f"    {listing['address']}  {units}  {listing['eoi']}")
            if notify and current["has_listings"]:
                send_notifications(current["listings"], load_subscribers())
            stored["hash"]         = current["hash"]
            stored["last_changed"] = now
        else:
            print(f"  No change — {len(current['listings'])} listing(s)")

        # Always sync listings — EOI filter may clear entries even when page hash is unchanged
        stored["has_listings"] = current["has_listings"]
        stored["listings"]     = current["listings"]
        stored["summary"]      = current["summary"]
        stored["last_checked"] = now
        save_state(stored)
        return stored

    except Exception as e:
        print(f"  Error: {e}")
        return load_state()


if __name__ == "__main__":
    state = check()
    print("\nCurrent state:")
    for listing in state.get("listings", []):
        units = "  ·  ".join(f"{u['count']}×{u['type']}" for u in listing.get("units", []))
        print(f"  {listing['address']}  —  {units}")
        if listing.get("eoi"):
            print(f"    {listing['eoi']}")
