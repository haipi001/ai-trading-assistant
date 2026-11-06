from app.core.config import Settings


def test_default_backend_cors_origins_cover_current_frontend_hosts() -> None:
    settings = Settings()
    assert "http://localhost:3002" in settings.backend_cors_origins
    assert "http://127.0.0.1:3002" in settings.backend_cors_origins
    assert "https://haipi001.github.io" in settings.backend_cors_origins
    assert "http://localhost:8850" in settings.backend_cors_origins
    assert "http://127.0.0.1:8850" in settings.backend_cors_origins
    assert "*" not in settings.backend_cors_origins
