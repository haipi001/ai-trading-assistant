#!/bin/bash
cd "$(dirname "$0")" || exit 1
if ! command -v npm >/dev/null 2>&1; then
  printf '%s\n' 'Node.js / npm 未找到，请先安装后再启动旧版前端。'
  exit 1
fi
if ! lsof -tiTCP:3002 -sTCP:LISTEN >/dev/null 2>&1; then
  npm run dev -- --host 127.0.0.1 --port 3002 >/tmp/r127-frontend-3002.log 2>&1 &
  sleep 1
fi
open 'http://localhost:3002/'
