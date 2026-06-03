#!/bin/sh
python scripts/geocode_toronto_housing.py
python scripts/map_toronto_housing.py
python poller.py &
gunicorn --workers 1 --bind 0.0.0.0:$PORT server:app
