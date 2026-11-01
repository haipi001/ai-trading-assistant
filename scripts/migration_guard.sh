#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
ALEMBIC="$BACKEND_DIR/.venv/bin/alembic"

if [ ! -x "$ALEMBIC" ]; then
  echo "migration guard requires backend/.venv/bin/alembic" >&2
  exit 1
fi

HEAD_COUNT="$(cd "$BACKEND_DIR" && "$ALEMBIC" heads | grep -c '(head)')"
if [ "$HEAD_COUNT" -ne 1 ]; then
  echo "migration guard requires exactly one Alembic head; found $HEAD_COUNT" >&2
  exit 1
fi

TEMP_DIR="$(mktemp -d -t ai-trading-os-migration-guard.XXXXXX)"
DATABASE_URL="sqlite+pysqlite:///$TEMP_DIR/guard.sqlite"
cleanup() {
  rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

cd "$BACKEND_DIR"
export DATABASE_URL
export LEGACY_TENANT_USER_ID="migration-guard-owner"

"$ALEMBIC" upgrade head
"$ALEMBIC" check
CURRENT_REVISION="$("$ALEMBIC" current | tail -n 1)"
if [[ "$CURRENT_REVISION" != *"(head)"* ]]; then
  echo "database did not reach the Alembic head: $CURRENT_REVISION" >&2
  exit 1
fi

"$ALEMBIC" downgrade -1
"$ALEMBIC" upgrade head
"$ALEMBIC" check

echo "Migration guard passed: one head, fresh upgrade, metadata parity, downgrade -1, and re-upgrade."
