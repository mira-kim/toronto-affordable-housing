#!/bin/sh
python geocode_toronto_housing.py
python map_toronto_housing.py
python poller.py &
gunicorn --workers 1 --bind 0.0.0.0:$PORT server:app
