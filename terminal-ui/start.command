#!/bin/bash
cd "$(dirname "$0")" || exit 1
terminal_root="$PWD"
if [ ! -f "features/terminal-feature.html" ]; then
  printf '%s\n' '正在构建业务功能面板…'
  if [ -f "../vite.terminal.config.mjs" ]; then
    terminal_project="$(cd .. && pwd)"
  elif [ -f "../ai-trading-assistant/vite.terminal.config.mjs" ]; then
    terminal_project="$(cd ../ai-trading-assistant && pwd)"
  else
    printf '%s\n' '找不到业务面板构建项目，请保留终端与 ai-trading-assistant 的目录结构。'
    exit 1
  fi
  (cd "$terminal_project" && TERMINAL_FEATURE_OUTDIR="$terminal_root/features" npm run build:terminal) || exit 1
fi
# Start the local API used by the embedded panels before opening the UI.
if ! curl --noproxy '*' --fail --silent --max-time 2 --output /dev/null http://127.0.0.1:8001/health/status; then
  if lsof -tiTCP:8001 -sTCP:LISTEN >/dev/null 2>&1; then
    printf '%s\n' '8001 端口已占用但后端未就绪，请检查服务。'
    exit 1
  fi
  nohup bash "$terminal_root/../scripts/start-trading-backend.sh" >/tmp/trading-backend-8001.log 2>&1 </dev/null &
  backend_ready=false
  for backend_attempt in {1..40}; do
    if curl --noproxy '*' --fail --silent --max-time 1 --output /dev/null http://127.0.0.1:8001/health/status; then
      backend_ready=true
      break
    fi
    sleep 0.25
  done
  if [ "$backend_ready" != true ]; then
    printf '%s\n' '后端未能启动，请检查 /tmp/trading-backend-8001.log。'
    exit 1
  fi
fi
PORT=8850
if ! lsof -tiTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1; then
  python3 scripts/serve.py --port "$PORT" >/tmp/terminal-ui-server.log 2>&1 &
fi
terminal_ready=false
for terminal_attempt in {1..40}; do
  if curl --noproxy '*' --fail --silent --max-time 1 --output /dev/null "http://127.0.0.1:$PORT/index.html" &&
     curl --noproxy '*' --fail --silent --max-time 1 --output /dev/null "http://127.0.0.1:$PORT/features/terminal-feature.html"; then
    terminal_ready=true
    break
  fi
  sleep 0.25
done
if [ "$terminal_ready" != true ]; then
  printf '%s\n' '前端入口或业务面板尚未就绪，请检查 8850 端口及 /tmp/terminal-ui-server.log 后重试。'
  exit 1
fi
open "http://127.0.0.1:$PORT/index.html"
