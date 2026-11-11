#!/bin/sh
cd "$(dirname "$0")"
python3 -m pip install -r requirements.txt
HOST=0.0.0.0 python3 app.py
