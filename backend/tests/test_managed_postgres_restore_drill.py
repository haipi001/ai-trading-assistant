from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "managed_postgres_restore_drill.py"
SPEC = spec_from_file_location("managed_postgres_restore_drill", SCRIPT)
assert SPEC and SPEC.loader
drill = module_from_spec(SPEC)
SPEC.loader.exec_module(drill)


def test_production_target_requires_remote_postgres_and_tls() -> None:
    assert drill.validate_target(
        "postgresql+psycopg://operator:secret@db.example/atos?sslmode=verify-full",
        "production",
    ) == []
    errors = drill.validate_target("postgresql://operator:secret@localhost/atos", "production")
    assert any("local/container" in error for error in errors)
    assert any("TLS" in error for error in errors)


def test_connection_parts_decode_without_exposing_password_in_tool_arguments() -> None:
    parts = drill.connection_parts("postgresql+psycopg://operator:p%40ss@db.example:6432/atos?sslmode=require")
    assert parts == {"host": "db.example", "port": 6432, "user": "operator", "password": "p@ss", "database": "atos"}
    arguments = drill.tool_connection_args(parts, "atos_restore")
    assert "p@ss" not in arguments
    assert "atos_restore" in arguments
    assert drill.tool_environment(parts)["PGPASSWORD"] == "p@ss"


def test_database_fingerprint_is_redacted_and_stable() -> None:
    first = drill.connection_parts("postgresql://a:first@db.example/atos")
    second = drill.connection_parts("postgresql://b:second@db.example/atos")
    assert drill.fingerprint(first) == drill.fingerprint(second)
    assert "db.example" not in drill.fingerprint(first)
