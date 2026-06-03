"""
Standalone poller — run as a separate process (or Docker service).
Checks TCHC listings every CHECK_INTERVAL_HOURS, emails subscribers on change,
and rebuilds the map HTML so data stays fresh.
"""

import time

from dotenv import load_dotenv

load_dotenv()

from config import CHECK_INTERVAL_HOURS
from monitor_tchc import check
from scripts.map_toronto_housing import run as rebuild_map

check(notify=False)  # initial check on startup — no emails
while True:
    time.sleep(CHECK_INTERVAL_HOURS * 3600)
    check(notify=True)
    rebuild_map()
