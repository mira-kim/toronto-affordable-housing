"""
Toronto Housing Map — Web Server
Serves the map and handles listing subscriptions.

Production (Docker / gunicorn):
    gunicorn --workers 1 --bind 0.0.0.0:5001 server:app

Local dev:
    python server.py
"""

import os
import re
import time
from collections import defaultdict

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request, send_file

load_dotenv()

from config import MAP_FILE, PORT, RATE_LIMIT, RATE_WINDOW
from monitor_tchc import add_subscriber, init_db, load_state, remove_subscriber, send_confirmation

_EMAIL_RE = re.compile(r'^[^@\s]{1,64}@[^@\s]{1,253}\.[^@\s.]{2,}$')
_sub_attempts: dict[str, list[float]] = defaultdict(list)

app = Flask(__name__)
init_db()  # runs on gunicorn import and on direct invocation


def _is_rate_limited(ip: str) -> bool:
    now    = time.time()
    cutoff = now - RATE_WINDOW
    recent = [t for t in _sub_attempts[ip] if t > cutoff]
    _sub_attempts[ip] = recent
    if len(recent) >= RATE_LIMIT:
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
    if added:
        send_confirmation(email)
    msg = "Subscribed! Check your email for a confirmation." if added else "Already subscribed."
    return jsonify({"ok": True, "added": added, "message": msg})


@app.route("/api/unsubscribe", methods=["GET"])
def api_unsubscribe():
    email = request.args.get("email", "").strip().lower()
    token = request.args.get("token", "").strip()
    if not email or not token:
        return "<p>Invalid unsubscribe link.</p>", 400
    removed = remove_subscriber(email, token)
    if removed:
        return "<p>You have been unsubscribed successfully.</p>", 200
    return "<p>Unsubscribe link is invalid or already used.</p>", 400


# ── Local dev entry point ─────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\nToronto Housing Map — http://localhost:{PORT}")
    print("Run poller.py separately to check listings.\n")
    app.run(port=PORT, debug=False)
