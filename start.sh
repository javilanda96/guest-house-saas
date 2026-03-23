#!/usr/bin/env bash
set -e

# RUN_BOT: controla si el proceso bot.py arranca junto con la API.
# Valor por defecto: enabled (comportamiento actual sin cambios).
# Poner RUN_BOT=false (o 0/no/off) para deshabilitar el bot y dejar
# solo la API activa — util para validar decay del heartbeat en produccion.
_run_bot=$(echo "${RUN_BOT:-true}" | tr '[:upper:]' '[:lower:]')
if [[ "$_run_bot" != "false" && "$_run_bot" != "0" && "$_run_bot" != "no" && "$_run_bot" != "off" ]]; then
    python -u bot.py &
else
    echo "[start.sh] RUN_BOT=$RUN_BOT — bot loop deshabilitado, solo API"
fi

exec uvicorn api:app --host 0.0.0.0 --port $PORT
