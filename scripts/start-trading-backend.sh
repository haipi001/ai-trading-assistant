#!/bin/sh
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
backend_dir="$script_dir/../backend"
trading_python="${TRADING_PYTHON:-$backend_dir/.venv/bin/python}"
if [ ! -x "$trading_python" ]; then
  echo 'Create backend/.venv and install backend dependencies, or set TRADING_PYTHON.' >&2
  exit 1
fi
cd "$backend_dir"
export RUNTIME_SCHEDULER_ENABLED=false
exec "$trading_python" -m uvicorn app.main:app --host 127.0.0.1 --port "${TRADING_API_PORT:-8001}"
