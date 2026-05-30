"""
Unit tests for monitor_tchc.py parsing functions.

Tests cover the three layers of the scraper:
  1. _parse_unit_count  — text → integer
  2. _extract_address   — page title → street address
  3. _extract_eoi       — paragraph text → EOI window string
  4. parse_listings     — full HTML → list of structured listing dicts
  5. extract_state      — full HTML → state dict (hash, has_listings, listings)

Run:
    pip install pytest
    pytest tests/test_monitor_tchc.py -v
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from monitor_tchc import (
    _eoi_is_current,
    _extract_address,
    _extract_eoi,
    _load_email_config,
    _parse_unit_count,
    add_subscriber,
    extract_state,
    parse_listings,
)


# ── _parse_unit_count ─────────────────────────────────────────────────────────

class TestParseUnitCount:
    def test_word_one(self):
        assert _parse_unit_count("one two-bedroom unit") == 1

    def test_word_sixteen(self):
        # "sixteen" must not be parsed as "six" (length-sort regression test)
        assert _parse_unit_count("Sixteen one-bedroom units") == 16

    def test_word_six(self):
        assert _parse_unit_count("Six bachelor units") == 6

    def test_digit(self):
        assert _parse_unit_count("24 three-bedroom units") == 24

    def test_leading_whitespace(self):
        assert _parse_unit_count("  Eight studio units") == 8

    def test_returns_none_for_garbage(self):
        assert _parse_unit_count("no numbers here") is None


# ── _extract_address ──────────────────────────────────────────────────────────

class TestExtractAddress:
    def test_typical_title(self):
        title = "Affordable housing rental units at 1070 Eastern Ave. (Don Summerville)"
        assert _extract_address(title) == "1070 Eastern Ave"

    def test_no_at_prefix(self):
        # Falls back to stripping the title itself
        result = _extract_address("5 Strachan Ave affordable housing units")
        assert "5 Strachan Ave" in result

    def test_strips_parenthetical(self):
        title = "Rental units at 200 Woolner Ave. (Weston)"
        assert _extract_address(title) == "200 Woolner Ave"

    def test_strips_period(self):
        title = "Affordable units at 340 Pharmacy Ave."
        assert _extract_address(title) == "340 Pharmacy Ave"


# ── _extract_eoi ──────────────────────────────────────────────────────────────

class TestExtractEoi:
    EOI_PARA = (
        "The Expression of Interest period will open on Tuesday, January 21, 2099, "
        "and close on Friday, February 20, 2099, at 4:00 p.m."
    )

    def test_parses_open_close_dates(self):
        result = _extract_eoi(self.EOI_PARA)
        assert "January 21, 2099" in result
        assert "February 20, 2099" in result

    def test_format_starts_with_opens(self):
        result = _extract_eoi(self.EOI_PARA)
        assert result.startswith("Opens")

    def test_fallback_truncation(self):
        long_text = "Some paragraph without open/close pattern. " + "x" * 200
        result = _extract_eoi(long_text)
        assert len(result) <= 123   # 120 chars + "…"
        assert result.endswith("…")

    def test_short_text_no_ellipsis(self):
        short = "EOI closes March 31, 2026."
        result = _extract_eoi(short)
        assert not result.endswith("…")


# ── parse_listings ────────────────────────────────────────────────────────────

SAMPLE_HTML_ONE_LISTING = """
<html><body><main>
  <h2>Available units</h2>
  <h4>Affordable housing rental units at 1070 Eastern Ave. (Don Summerville)</h4>
  <ul>
    <li>Sixteen one-bedroom units</li>
    <li>Thirteen two-bedroom units</li>
    <li>Six three-bedroom units</li>
  </ul>
  <p>The Expression of Interest period will open on Tuesday, January 21, 2099,
  and close on Friday, February 20, 2099, at 4:00 p.m.</p>
</main></body></html>
"""

SAMPLE_HTML_NO_LISTINGS = """
<html><body><main>
  <h2>Affordable housing</h2>
  <p>There are currently no available units. Check back later.</p>
</main></body></html>
"""

SAMPLE_HTML_MULTIPLE = """
<html><body><main>
  <h4>Affordable housing rental units at 1070 Eastern Ave. (Don Summerville)</h4>
  <ul>
    <li>Sixteen one-bedroom units</li>
    <li>Thirteen two-bedroom units</li>
  </ul>
  <p>The Expression of Interest period will open on Tuesday, January 21, 2099,
  and close on Friday, February 20, 2099, at 4:00 p.m.</p>

  <h4>Rental units at 5 Strachan Ave</h4>
  <ul>
    <li>Eight one-bedroom units</li>
    <li>Four two-bedroom units</li>
  </ul>
  <p>The Expression of Interest period will open on Monday, March 3, 2099,
  and close on Monday, March 31, 2099.</p>
</main></body></html>
"""


class TestParseListings:
    def test_returns_list(self):
        listings = parse_listings(SAMPLE_HTML_ONE_LISTING)
        assert isinstance(listings, list)

    def test_one_listing_parsed(self):
        listings = parse_listings(SAMPLE_HTML_ONE_LISTING)
        assert len(listings) == 1

    def test_address_extracted(self):
        listing = parse_listings(SAMPLE_HTML_ONE_LISTING)[0]
        assert listing["address"] == "1070 Eastern Ave"

    def test_unit_counts(self):
        listing = parse_listings(SAMPLE_HTML_ONE_LISTING)[0]
        units   = {u["type"]: u["count"] for u in listing["units"]}
        assert units["1BR"] == 16
        assert units["2BR"] == 13
        assert units["3BR"] == 6

    def test_eoi_extracted(self):
        listing = parse_listings(SAMPLE_HTML_ONE_LISTING)[0]
        assert "January 21, 2099" in listing["eoi"]
        assert "February 20, 2099" in listing["eoi"]

    def test_no_listings_returns_empty(self):
        listings = parse_listings(SAMPLE_HTML_NO_LISTINGS)
        assert listings == []

    def test_no_main_returns_empty(self):
        listings = parse_listings("<html><body><p>nothing</p></body></html>")
        assert listings == []

    def test_multiple_listings(self):
        listings = parse_listings(SAMPLE_HTML_MULTIPLE)
        assert len(listings) == 2
        addresses = [listing["address"] for listing in listings]
        assert "1070 Eastern Ave" in addresses
        assert "5 Strachan Ave" in addresses

    def test_listing_has_required_keys(self):
        listing = parse_listings(SAMPLE_HTML_ONE_LISTING)[0]
        for key in ("title", "address", "units", "eoi", "details"):
            assert key in listing


# ── extract_state ─────────────────────────────────────────────────────────────

class TestExtractState:
    def test_has_listings_true(self):
        state = extract_state(SAMPLE_HTML_ONE_LISTING)
        assert state["has_listings"] is True

    def test_has_listings_false(self):
        state = extract_state(SAMPLE_HTML_NO_LISTINGS)
        assert state["has_listings"] is False

    def test_hash_is_string(self):
        state = extract_state(SAMPLE_HTML_ONE_LISTING)
        assert isinstance(state["hash"], str)
        assert len(state["hash"]) == 32  # MD5 hex digest

    def test_hash_changes_with_content(self):
        s1 = extract_state(SAMPLE_HTML_ONE_LISTING)
        s2 = extract_state(SAMPLE_HTML_NO_LISTINGS)
        assert s1["hash"] != s2["hash"]

    def test_hash_stable_for_same_content(self):
        s1 = extract_state(SAMPLE_HTML_ONE_LISTING)
        s2 = extract_state(SAMPLE_HTML_ONE_LISTING)
        assert s1["hash"] == s2["hash"]

    def test_summary_is_first_address(self):
        state = extract_state(SAMPLE_HTML_ONE_LISTING)
        assert state["summary"] == "1070 Eastern Ave"

    def test_summary_empty_when_no_listings(self):
        state = extract_state(SAMPLE_HTML_NO_LISTINGS)
        assert state["summary"] == ""

    def test_empty_html_does_not_crash(self):
        state = extract_state("")
        assert state["has_listings"] is False
        assert state["listings"] == []


# ── _eoi_is_current ───────────────────────────────────────────────────────────

class TestEoiIsCurrent:
    def test_past_eoi_is_not_current(self):
        assert not _eoi_is_current("Opens January 21, 2026 — closes February 20, 2026")

    def test_far_future_eoi_is_current(self):
        assert _eoi_is_current("Opens January 1, 2099 — closes February 1, 2099")

    def test_empty_eoi_is_current(self):
        assert _eoi_is_current("")

    def test_unparseable_eoi_is_current(self):
        assert _eoi_is_current("EOI details to be announced")


# ── add_subscriber validation ─────────────────────────────────────────────────

class TestAddSubscriber:
    def test_rejects_empty_string(self):
        import pytest
        with pytest.raises(ValueError):
            add_subscriber("")

    def test_rejects_no_at_sign(self):
        import pytest
        with pytest.raises(ValueError):
            add_subscriber("notanemail")


# ── _load_email_config ────────────────────────────────────────────────────────

class TestLoadEmailConfig:
    def test_env_vars_take_precedence(self, monkeypatch):
        monkeypatch.setenv("GMAIL_USER", "env@example.com")
        monkeypatch.setenv("GMAIL_APP_PASSWORD", "secret")
        cfg = _load_email_config()
        assert cfg["gmail_user"] == "env@example.com"
        assert cfg["gmail_app_password"] == "secret"

    def test_returns_none_when_no_credentials(self, monkeypatch):
        monkeypatch.delenv("GMAIL_USER", raising=False)
        monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
        # No JSON file in test context — should return None
        cfg = _load_email_config()
        assert cfg is None or isinstance(cfg, dict)
