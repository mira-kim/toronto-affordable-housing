"""
Tests for the data_sources package and map build pipeline.

Critical coverage:
  1. fetch_all() — one failing source must not crash the map build
  2. ckan_units.fetch() — building grouping and key shape
  3. build_html() — all template placeholders are replaced
"""

import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import data_sources
from data_sources import ckan_units
from scripts.map_toronto_housing import build_html


# ── fetch_all error isolation ─────────────────────────────────────────────────

class TestFetchAll:
    def _make_source(self, name, return_value=None, raises=None):
        m = MagicMock()
        m.__name__ = name
        if raises:
            m.fetch.side_effect = raises
        else:
            m.fetch.return_value = return_value
        return m

    def test_one_failing_source_does_not_crash(self):
        good = self._make_source("good", return_value={"waitlist": {"latest": {}}})
        bad  = self._make_source("bad",  raises=RuntimeError("network timeout"))

        with patch.object(data_sources, "SOURCES", [good, bad]):
            result = data_sources.fetch_all()

        assert "waitlist" in result

    def test_all_sources_merged(self):
        a = self._make_source("a", return_value={"key_a": 1})
        b = self._make_source("b", return_value={"key_b": 2})

        with patch.object(data_sources, "SOURCES", [a, b]):
            result = data_sources.fetch_all()

        assert result == {"key_a": 1, "key_b": 2}

    def test_all_failing_returns_empty_dict(self):
        bad = self._make_source("bad", raises=Exception("boom"))

        with patch.object(data_sources, "SOURCES", [bad]):
            result = data_sources.fetch_all()

        assert result == {}


# ── ckan_units building grouping ──────────────────────────────────────────────

MOCK_UNIT_RECORDS = [
    {
        "Building Complex Name": "Parkview Coop",
        "Unit Size": "1B",
        "Household Income Limit": "62500",
        "Units Available in the Last 12 Months": "2",
        "Number of Subsidized Units": "20",
        "Number of Market Rent Units": "5",
        "Mandate Description": None,
    },
    {
        "Building Complex Name": "Parkview Coop",
        "Unit Size": "2B",
        "Household Income Limit": "75000",
        "Units Available in the Last 12 Months": "0",
        "Number of Subsidized Units": "10",
        "Number of Market Rent Units": "3",
        "Mandate Description": None,
    },
    {
        "Building Complex Name": "Elm Street Housing",
        "Unit Size": "Bachelor",
        "Household Income Limit": "45000",
        "Units Available in the Last 12 Months": "1",
        "Number of Subsidized Units": "8",
        "Number of Market Rent Units": "2",
        "Mandate Description": "Seniors",
    },
]


def _mock_ckan_get(records):
    """Return a mock requests.get that yields records then empty to stop pagination."""
    responses = [
        MagicMock(**{"json.return_value": {"result": {"records": records, "total": len(records)}}}),
        MagicMock(**{"json.return_value": {"result": {"records": [], "total": len(records)}}}),
    ]
    m = MagicMock(side_effect=responses)
    for r in responses:
        r.raise_for_status = MagicMock()
    return m


class TestCkanUnits:
    def test_groups_by_building_name(self):
        with patch("data_sources.ckan_units.requests.get", _mock_ckan_get(MOCK_UNIT_RECORDS)):
            result = ckan_units.fetch()

        by = result["units_by_building"]
        assert "Parkview Coop" in by
        assert "Elm Street Housing" in by
        assert len(by["Parkview Coop"]) == 2

    def test_unit_row_has_required_keys(self):
        with patch("data_sources.ckan_units.requests.get", _mock_ckan_get(MOCK_UNIT_RECORDS)):
            result = ckan_units.fetch()

        unit = result["units_by_building"]["Parkview Coop"][0]
        for key in ("unit_size", "income_limit", "available_last_12m",
                    "subsidized_units", "market_units", "mandate"):
            assert key in unit, f"missing key: {key}"

    def test_skips_records_with_empty_building_name(self):
        records = MOCK_UNIT_RECORDS + [{
            "Building Complex Name": "",
            "Unit Size": "1B",
            "Household Income Limit": "50000",
            "Units Available in the Last 12 Months": "0",
            "Number of Subsidized Units": "5",
            "Number of Market Rent Units": "1",
            "Mandate Description": None,
        }]
        with patch("data_sources.ckan_units.requests.get", _mock_ckan_get(records)):
            result = ckan_units.fetch()

        assert "" not in result["units_by_building"]


# ── build_html placeholder injection ─────────────────────────────────────────

MINIMAL_BUILDINGS = [
    {"Building Complex Name": "Test Tower", "lat": 43.7, "lon": -79.4, "Ward": "1"}
]

MINIMAL_DATA = {
    "waitlist": {
        "latest":   {"Quarter": "Q1 2025", "Subsidized Housing Units": "85000", "Affordable Housing Units": "6500"},
        "previous": None,
    },
    "units_by_building": {
        "Test Tower": [{"unit_size": "1B", "income_limit": "62500",
                        "available_last_12m": "1", "subsidized_units": "20",
                        "market_units": "5", "mandate": None}],
    },
}

PLACEHOLDERS = [
    "__BUILDINGS__", "__WAITLIST__", "__OPTIONS__", "__UNITS_BY_BUILDING__",
    "__APPLY_URL__", "__COHB_URL__", "__TCHC_AFFORDABLE_URL__",
]


class TestBuildHtml:
    def test_all_placeholders_replaced(self):
        html = build_html(MINIMAL_BUILDINGS, MINIMAL_DATA)
        for p in PLACEHOLDERS:
            assert p not in html, f"placeholder not replaced: {p}"

    def test_units_by_building_data_present(self):
        html = build_html(MINIMAL_BUILDINGS, MINIMAL_DATA)
        assert "Test Tower" in html

    def test_missing_data_sources_does_not_crash(self):
        # data_sources all failed — empty dict passed in
        html = build_html(MINIMAL_BUILDINGS, {})
        for p in PLACEHOLDERS:
            assert p not in html, f"placeholder not replaced with empty data: {p}"
