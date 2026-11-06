#!/bin/bash
cd "$(dirname "$0")" || exit 1
if [ ! -f "features/terminal-feature.html" ]; then
  printf '%s\n' '正在构建业务功能面板…'
  (cd ../ai-trading-assistant && npm run build:terminal) || exit 1
fi
PORT=8850
if ! lsof -tiTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
  python3 scripts/serve.py --port "$PORT" >/tmp/terminal-ui-server.log 2>&1 &
  sleep 1
fi
open "http://127.0.0.1:$PORT/index.html"
