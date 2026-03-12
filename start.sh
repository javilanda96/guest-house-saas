#!/usr/bin/env bash
set -e
python bot.py &
exec uvicorn api:app --host 0.0.0.0 --port $PORT
