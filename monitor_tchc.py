"""
TCHC Affordable Rent Monitor
Scrapes torontohousing.ca for new listings and notifies subscribers by email.

Setup (.env file):
  SENDGRID_API_KEY=SG.xxxx
  SENDGRID_FROM=you@yourdomain.com
  APP_BASE_URL=http://localhost:5001
"""

import hashlib
import hmac
import json
import os
import re
import sqlite3
from datetime import datetime
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from config import DB_FILE, FETCH_TIMEOUT, STATE_FILE, TCHC_URL, USER_AGENT

load_dotenv()

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
        timeout=FETCH_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
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

def init_db():
    os.makedirs("data", exist_ok=True)
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                email      TEXT PRIMARY KEY,
                token      TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)


def _make_token(email: str) -> str:
    key = os.environ.get("SENDGRID_API_KEY", "").encode()
    return hmac.new(key, email.encode(), hashlib.sha256).hexdigest()


def load_subscribers() -> list[str]:
    if not os.path.exists(DB_FILE):
        return []
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("SELECT email FROM subscribers").fetchall()
    return [r[0] for r in rows]


def add_subscriber(email: str) -> bool:
    if not email or "@" not in email:
        raise ValueError(f"Invalid email: {email!r}")
    init_db()
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute(
                "INSERT INTO subscribers (email, token, created_at) VALUES (?,?,?)",
                (email, _make_token(email), datetime.now().isoformat()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def remove_subscriber(email: str, token: str) -> bool:
    if not os.path.exists(DB_FILE):
        return False
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.execute(
            "DELETE FROM subscribers WHERE email=? AND token=?", (email, token)
        )
    return cur.rowcount > 0


# ── Email ─────────────────────────────────────────────────────────────────────

def _sendgrid_credentials() -> tuple[str | None, str | None, str]:
    return (
        os.environ.get("SENDGRID_API_KEY"),
        os.environ.get("SENDGRID_FROM"),
        os.environ.get("APP_BASE_URL", "http://localhost:5001"),
    )


def send_confirmation(email: str):
    api_key, from_email, base_url = _sendgrid_credentials()
    if not api_key or not from_email:
        return

    token  = _make_token(email)
    unsub  = f"{base_url}/api/unsubscribe?{urlencode({'email': email, 'token': token})}"
    body   = (
        "You're now subscribed to Toronto Affordable Housing Map alerts.\n\n"
        "You'll receive an email when new TCHC affordable rent units become available "
        "at torontohousing.ca.\n\n"
        f"View the map: {base_url}\n\n"
        f"Unsubscribe: {unsub}"
    )
    try:
        msg = Mail(
            from_email=from_email,
            to_emails=email,
            subject="You're subscribed to TCHC housing alerts",
            plain_text_content=body,
        )
        SendGridAPIClient(api_key).client.mail.send.post(request_body=msg.get())
    except Exception as e:
        print(f"  Confirmation send failed: {e}")


def send_notifications(listings: list[dict], subscribers: list[str]):
    if not subscribers:
        return

    api_key, from_email, base_url = _sendgrid_credentials()
    if not api_key or not from_email:
        print("  No SendGrid credentials (set SENDGRID_API_KEY and SENDGRID_FROM in .env)")
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
    lines.append(f"View and apply: {TCHC_URL}\n")

    sg   = SendGridAPIClient(api_key)
    sent = failed = 0
    for email in subscribers:
        token   = _make_token(email)
        unsub   = f"{base_url}/api/unsubscribe?{urlencode({'email': email, 'token': token})}"
        body    = "\n".join(lines) + f"Unsubscribe: {unsub}"
        try:
            msg = Mail(
                from_email=from_email,
                to_emails=email,
                subject=subject,
                plain_text_content=body,
            )
            sg.client.mail.send.post(request_body=msg.get())
            sent += 1
        except Exception as e:
            print(f"  Send failed: {e}")
            failed += 1
    print(f"  Notified {sent} subscriber(s), {failed} failed")


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
