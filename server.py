"""
Toronto Housing Map — Local Server
Serves the map and handles listing checks and email subscriptions.

Usage:
    pip install flask
    python server.py

Then open http://localhost:5001 in your browser.
The TCHC listing page is checked every CHECK_INTERVAL_HOURS hours automatically.
"""

import os
import re
import threading
import time
from collections import defaultdict

from flask import Flask, abort, jsonify, request, send_file

from monitor_tchc import add_subscriber, check, load_state

MAP_FILE             = os.path.join("data", "toronto_housing_map.html")
CHECK_INTERVAL_HOURS = 6
PORT                 = 5001

_EMAIL_RE      = re.compile(r'^[^@\s]{1,64}@[^@\s]{1,253}\.[^@\s.]{2,}$')
_RATE_WINDOW   = 60   # seconds
_RATE_LIMIT    = 5    # max subscribe attempts per IP per window
_sub_attempts: dict[str, list[float]] = defaultdict(list)

app = Flask(__name__)


def _is_rate_limited(ip: str) -> bool:
    now     = time.time()
    cutoff  = now - _RATE_WINDOW
    recent  = [t for t in _sub_attempts[ip] if t > cutoff]
    _sub_attempts[ip] = recent
    if len(recent) >= _RATE_LIMIT:
        return True
    _sub_attempts[ip].append(now)
    return False


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def serve_map():
    if not os.path.exists(MAP_FILE):
        abort(404, "Map not generated yet — run map_toronto_housing.py first.")
    return send_file(os.path.abspath(MAP_FILE))


@app.route("/api/listings")
def api_listings():
    state = load_state()
    return jsonify({
        "has_listings": state.get("has_listings", False),
        "listings":     state.get("listings", []),
        "summary":      state.get("summary", ""),
        "last_checked": state.get("last_checked"),
        "last_changed": state.get("last_changed"),
    })


@app.route("/api/subscribe", methods=["POST"])
def api_subscribe():
    if _is_rate_limited(request.remote_addr):
        return jsonify({"ok": False, "error": "Too many requests — try again later."}), 429
    data  = request.get_json(silent=True) or {}
    email = str(data.get("email") or "").strip().lower()
    if not _EMAIL_RE.match(email):
        return jsonify({"ok": False, "error": "Enter a valid email address"}), 400
    added = add_subscriber(email)
    msg   = "Subscribed! You'll be notified when new TCHC units open." if added else "Already subscribed."
    return jsonify({"ok": True, "added": added, "message": msg})


# ── Background poller ─────────────────────────────────────────────────────────

def _poller():
    check(notify=False)          # initial check on startup — no emails
    while True:
        time.sleep(CHECK_INTERVAL_HOURS * 3600)
        try:
            check(notify=True)
        except Exception as e:
            print(f"  Poller error: {e}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    t = threading.Thread(target=_poller, daemon=True)
    t.start()

    print("\nToronto Housing Map server running")
    print(f"  Map:  http://localhost:{PORT}")
    print(f"  TCHC listings checked every {CHECK_INTERVAL_HOURS} hours")
    print("  Press Ctrl+C to stop\n")

    app.run(port=PORT, debug=False)
