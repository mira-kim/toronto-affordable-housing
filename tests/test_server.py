"""
Functional tests for server.py — covers the security/robustness fixes:
  - Email regex rejects bad addresses, accepts valid ones
  - Rate limiter blocks after N attempts per window
  - /api/subscribe enforces both (via Flask test client)
  - /api/listings returns the listings array
  - /api/unsubscribe validates token and removes subscriber

Run:
    pytest tests/test_server.py -v
"""

import sys
import os
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import monitor_tchc
from monitor_tchc import _make_token, add_subscriber, init_db
from server import _EMAIL_RE, _is_rate_limited, _sub_attempts, app


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Redirect all subscriber DB operations to a fresh temp file per test."""
    db_path = str(tmp_path / "test_subscribers.db")
    monkeypatch.setattr(monitor_tchc, "DB_FILE", db_path)
    init_db()


# ── Email regex ───────────────────────────────────────────────────────────────

class TestEmailRegex:
    def test_valid(self):
        assert _EMAIL_RE.match("user@example.com")

    def test_valid_subdomain(self):
        assert _EMAIL_RE.match("user@mail.example.co.uk")

    def test_rejects_no_at(self):
        assert not _EMAIL_RE.match("userexample.com")

    def test_rejects_no_domain(self):
        assert not _EMAIL_RE.match("user@")

    def test_rejects_no_tld(self):
        assert not _EMAIL_RE.match("user@example")

    def test_rejects_spaces(self):
        assert not _EMAIL_RE.match("user @example.com")

    def test_rejects_double_at(self):
        assert not _EMAIL_RE.match("user@@example.com")


# ── Rate limiter ──────────────────────────────────────────────────────────────

class TestRateLimiter:
    def setup_method(self):
        _sub_attempts.clear()

    def test_allows_under_limit(self):
        for _ in range(4):
            assert not _is_rate_limited("1.2.3.4")

    def test_blocks_at_limit(self):
        for _ in range(5):
            _is_rate_limited("1.2.3.5")
        assert _is_rate_limited("1.2.3.5")

    def test_different_ips_are_independent(self):
        for _ in range(5):
            _is_rate_limited("10.0.0.1")
        assert not _is_rate_limited("10.0.0.2")

    def test_old_attempts_expire(self):
        # Manually insert a stale attempt well outside the 60s window
        _sub_attempts["1.2.3.6"] = [time.time() - 120]
        assert not _is_rate_limited("1.2.3.6")


# ── /api/subscribe endpoint ───────────────────────────────────────────────────

class TestSubscribeEndpoint:
    def setup_method(self):
        _sub_attempts.clear()
        self.client = app.test_client()

    def _post(self, email):
        return self.client.post(
            "/api/subscribe",
            json={"email": email},
            content_type="application/json",
        )

    def test_bad_email_returns_400(self):
        r = self._post("notanemail")
        assert r.status_code == 400
        assert r.get_json()["ok"] is False

    def test_rate_limit_returns_429(self):
        for _ in range(5):
            self._post("a@b.com")
        r = self._post("a@b.com")
        assert r.status_code == 429


# ── /api/listings returns listings field ─────────────────────────────────────

class TestListingsEndpoint:
    def setup_method(self):
        self.client = app.test_client()

    def test_listings_key_present(self):
        r = self.client.get("/api/listings")
        assert r.status_code == 200
        data = r.get_json()
        assert "listings" in data
        assert isinstance(data["listings"], list)

    def test_has_listings_key_present(self):
        r = self.client.get("/api/listings")
        assert "has_listings" in r.get_json()


# ── /api/unsubscribe endpoint ─────────────────────────────────────────────────

class TestUnsubscribeEndpoint:
    def setup_method(self):
        self.client = app.test_client()

    def test_valid_token_unsubscribes(self):
        add_subscriber("user@example.com")
        token = _make_token("user@example.com")
        r = self.client.get(f"/api/unsubscribe?email=user@example.com&token={token}")
        assert r.status_code == 200

    def test_wrong_token_returns_400(self):
        add_subscriber("user@example.com")
        r = self.client.get("/api/unsubscribe?email=user@example.com&token=badtoken")
        assert r.status_code == 400

    def test_missing_params_returns_400(self):
        r = self.client.get("/api/unsubscribe")
        assert r.status_code == 400

    def test_token_is_single_use(self):
        add_subscriber("user@example.com")
        token = _make_token("user@example.com")
        self.client.get(f"/api/unsubscribe?email=user@example.com&token={token}")
        r = self.client.get(f"/api/unsubscribe?email=user@example.com&token={token}")
        assert r.status_code == 400
