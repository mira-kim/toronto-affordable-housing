"""
Standalone poller — run as a separate process (or Docker service).
Checks TCHC listings every CHECK_INTERVAL_HOURS and emails subscribers on change.
"""

import time

from dotenv import load_dotenv

load_dotenv()

from monitor_tchc import check

CHECK_INTERVAL_HOURS = 6

check(notify=False)  # initial check on startup — no emails
while True:
    time.sleep(CHECK_INTERVAL_HOURS * 3600)
    check(notify=True)
