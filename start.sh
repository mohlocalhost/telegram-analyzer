#!/usr/bin/env bash
set -e
cd /app
python3 seed.py
python3 server.py --port "${PORT:-8080}"
