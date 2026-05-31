from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from codex_usage.web.app import create_app
from codex_usage.web.settings import (
    CONFIG_PATH_ENV,
    DB_PATH_ENV,
    load_web_settings,
)


def test_web_settings_prefers_env_db_path(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.db"

    settings = load_web_settings({DB_PATH_ENV: str(db_path)})

    assert settings.db_path == db_path
    assert settings.db_path_source == DB_PATH_ENV
    assert settings.db_exists is False


def test_web_settings_reads_configured_db_path(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    db_path = tmp_path / "data" / "codex_usage.db"
    config_path.write_text(
        f'[app]\nsqlite_db_path = "{db_path.as_posix()}"\n',
        encoding="utf-8",
    )

    settings = load_web_settings({CONFIG_PATH_ENV: str(config_path)})

    assert settings.db_path == db_path
    assert settings.db_path_source == str(config_path)
    assert settings.config_path == config_path


def test_homepage_shows_app_status_and_db_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "usage.db"
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "codex-usage" in response.text
    assert "running" in response.text
    assert "SQLite only" in response.text
    assert str(db_path) in response.text
    assert "missing" in response.text
