"""File-backed local secret store for user-imported credentials.

Local-first products cannot assume a cloud secret manager, but the codebase's
rule stands: secret values never enter the database, config payloads, logs, or
API responses. This store keeps user-imported secrets (LLM API keys, future
read-only exchange keys) in a gitignored, owner-only file next to `.env`,
loads them into process environment at startup, and hands out only `env://`
references for everything downstream.
"""

from __future__ import annotations

import os
import tempfile
import fcntl
from contextlib import contextmanager
import re
from pathlib import Path

_SECRET_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_STORE_FILENAME = ".user_secrets.env"


class LocalSecretError(ValueError):
    pass


def store_path() -> Path:
    return Path(__file__).resolve().parents[2] / _STORE_FILENAME


def _read_store() -> dict[str, str]:
    path = store_path()
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if _SECRET_NAME_PATTERN.match(name.strip()):
            values[name.strip()] = value
    return values


def _write_store(values: dict[str, str]) -> None:
    path = store_path()
    lines = ["# User-imported local secrets. Gitignored; never commit or sync this file."]
    lines += [f"{name}={value}" for name, value in sorted(values.items())]
    fd, temporary = tempfile.mkstemp(prefix=".secret-write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)

@contextmanager
def _store_lock():
    path = store_path().with_suffix('.env.lock')
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)



def load_user_secrets() -> int:
    """Load stored secrets into process environment at startup. Existing
    environment values win so an operator override is never clobbered."""
    values = _read_store()
    loaded = 0
    for name, value in values.items():
        if name not in os.environ:
            os.environ[name] = value
            loaded += 1
    return loaded


def set_user_secret(name: str, value: str) -> str:
    name = str(name or "").strip().upper()
    if not _SECRET_NAME_PATTERN.match(name):
        raise LocalSecretError("secret name must be UPPER_SNAKE_CASE, 3-64 chars, starting with a letter")
    value = str(value or "").strip()
    if not value:
        raise LocalSecretError("secret value must not be empty")
    if "\n" in value or "\r" in value:
        raise LocalSecretError("secret value must be a single line")
    with _store_lock():
        values = _read_store()
        values[name] = value
        _write_store(values)
    os.environ[name] = value
    return f"env://{name}"


def delete_user_secret(name: str) -> bool:
    name = str(name or "").strip().upper()
    with _store_lock():
        values = _read_store()
        existed = name in values
        if existed:
            del values[name]
            _write_store(values)
    os.environ.pop(name, None)
    return existed


def list_user_secret_names() -> list[dict[str, str]]:
    """Names and references only; values are never returned."""
    return [{"name": name, "reference": f"env://{name}"} for name in sorted(_read_store())]
