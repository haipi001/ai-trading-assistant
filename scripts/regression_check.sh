#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR/backend"
./.venv/bin/python -m pytest -q
cd "$ROOT_DIR"
./scripts/migration_guard.sh
npm run test:interactions
npm run test:models
npm run build
