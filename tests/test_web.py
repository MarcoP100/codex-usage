from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from codex_usage.db import import_token_events_to_sqlite
from codex_usage.web.app import create_app
from codex_usage.web.settings import (
    CONFIG_PATH_ENV,
    DB_PATH_ENV,
    load_web_settings,
)


MODEL_PRICING_USD_PER_MILLION = {
    "gpt-5.5": (5.0, 0.5, 30.0),
    "gpt-5.4": (2.5, 0.25, 15.0),
    "gpt-5.4-mini": (0.75, 0.075, 4.5),
}


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


def test_homepage_shows_sqlite_usage_kpis(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sessions_dir = tmp_path / "sessions"
    day_dir = sessions_dir / "2026" / "05" / "20"
    day_dir.mkdir(parents=True)
    session_file = day_dir / "rollout-web-report.jsonl"
    session_file.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-05-20T10:00:00Z","type":"turn_context","payload":{"model":"gpt-5.4","effort":"medium","cwd":"C:/repo/web-demo"}}',
                '{"timestamp":"2026-05-20T10:00:01Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":100,"cached_input_tokens":20,"output_tokens":10,"reasoning_output_tokens":5,"total_tokens":115}}}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "usage.db"
    import_token_events_to_sqlite(
        db_path=db_path,
        sessions_dir=sessions_dir,
        include_archived_sessions=False,
        source_device=None,
        source_account=None,
        pricing=MODEL_PRICING_USD_PER_MILLION,
        default_pricing=MODEL_PRICING_USD_PER_MILLION["gpt-5.5"],
    )
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "Covered period" in response.text
    assert "2026-05-20T10:00:01+00:00" in response.text
    assert "Total tokens" in response.text
    assert "115" in response.text
    assert "Cache ratio" in response.text
    assert "20.0%" in response.text
    assert "Top repositories" in response.text
    assert "web-demo" in response.text
    assert "Top models" in response.text
    assert "gpt-5.4" in response.text
    assert "Top events" in response.text


def test_homepage_handles_existing_empty_database(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "empty.db"
    db_path.write_bytes(b"")
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "SQLite database is not ready" in response.text


def test_homepage_filters_sqlite_usage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sessions_dir = tmp_path / "sessions"
    day_dir = sessions_dir / "2026" / "05" / "20"
    day_dir.mkdir(parents=True)
    session_file = day_dir / "rollout-web-filter-report.jsonl"
    session_file.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-05-20T10:00:00Z","type":"turn_context","payload":{"model":"gpt-5.4","effort":"medium","cwd":"C:/repo/keep"}}',
                '{"timestamp":"2026-05-20T10:00:01Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":100,"cached_input_tokens":20,"output_tokens":10,"reasoning_output_tokens":5,"total_tokens":115}}}}',
                '{"timestamp":"2026-05-20T11:00:00Z","type":"turn_context","payload":{"model":"gpt-5.4-mini","effort":"low","cwd":"C:/repo/keep"}}',
                '{"timestamp":"2026-05-20T11:00:01Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":50,"cached_input_tokens":10,"output_tokens":8,"reasoning_output_tokens":2,"total_tokens":60}}}}',
                '{"timestamp":"2026-05-21T10:00:00Z","type":"turn_context","payload":{"model":"gpt-5.4","effort":"medium","cwd":"C:/repo/drop"}}',
                '{"timestamp":"2026-05-21T10:00:01Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":70,"cached_input_tokens":7,"output_tokens":9,"reasoning_output_tokens":3,"total_tokens":82}}}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "usage.db"
    import_token_events_to_sqlite(
        db_path=db_path,
        sessions_dir=sessions_dir,
        include_archived_sessions=False,
        source_device=None,
        source_account=None,
        pricing=MODEL_PRICING_USD_PER_MILLION,
        default_pricing=MODEL_PRICING_USD_PER_MILLION["gpt-5.5"],
    )
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    client = TestClient(create_app())

    response = client.get(
        "/",
        params={
            "from": "2026-05-20",
            "to": "2026-05-20",
            "repository": "keep",
            "model": "gpt-5.4",
        },
    )

    assert response.status_code == 200
    assert 'value="2026-05-20"' in response.text
    assert 'value="keep"' in response.text
    assert 'value="gpt-5.4"' in response.text
    assert "Filtered view" in response.text
    assert "Total tokens" in response.text
    assert "115" in response.text
    assert "keep" in response.text
    assert "drop" not in response.text
    assert "gpt-5.4-mini" not in response.text


def test_homepage_shows_filter_validation_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "usage.db"
    db_path.write_bytes(b"")
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    client = TestClient(create_app())

    response = client.get("/", params={"from": "2026/05/20"})

    assert response.status_code == 200
    assert "--from must use YYYY-MM-DD format" in response.text
    assert 'value="2026/05/20"' in response.text
