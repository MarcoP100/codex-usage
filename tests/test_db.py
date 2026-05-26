from __future__ import annotations

import sqlite3
from pathlib import Path

from codex_usage.db import import_token_events_to_sqlite


MODEL_PRICING_USD_PER_MILLION = {
    "gpt-5.5": (5.0, 0.5, 30.0),
    "gpt-5.4": (2.5, 0.25, 15.0),
    "gpt-5.4-mini": (0.75, 0.075, 4.5),
    "gpt-5.3-codex": (1.75, 0.175, 14.0),
}


def test_import_sqlite_is_idempotent(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    day_dir = sessions_dir / "2026" / "05" / "20"
    day_dir.mkdir(parents=True)
    session_file = day_dir / "rollout-test.jsonl"
    session_file.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-05-20T10:00:00Z","type":"turn_context","payload":{"model":"gpt-5.4","effort":"medium","cwd":"C:/Progetti/personal/codex-usage"}}',
                '{"timestamp":"2026-05-20T10:00:01Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":100,"cached_input_tokens":20,"output_tokens":10,"reasoning_output_tokens":5,"total_tokens":110}}}}',
                '{"timestamp":"2026-05-20T10:00:02Z","type":"event_msg","payload":{"type":"task_started"}}',
                "{bad json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    db_path = tmp_path / "usage.db"
    first = import_token_events_to_sqlite(
        db_path=db_path,
        sessions_dir=sessions_dir,
        include_archived_sessions=False,
        source_device="laptop-1",
        source_account="me@example.com",
        pricing=MODEL_PRICING_USD_PER_MILLION,
        default_pricing=MODEL_PRICING_USD_PER_MILLION["gpt-5.5"],
    )
    second = import_token_events_to_sqlite(
        db_path=db_path,
        sessions_dir=sessions_dir,
        include_archived_sessions=False,
        source_device="laptop-1",
        source_account="me@example.com",
        pricing=MODEL_PRICING_USD_PER_MILLION,
        default_pricing=MODEL_PRICING_USD_PER_MILLION["gpt-5.5"],
    )

    assert first["inserted"] == 1
    assert second["inserted"] == 0
    assert second["skipped_duplicate"] == 1
    assert first["raw_inserted"] == 4
    assert second["raw_inserted"] == 0
    assert first["malformed_json_lines"] == 1
    assert first["missing_payload_type"] == 0
    assert first["missing_token_fields"] == 0
    assert first["non_token_events"] == 2
    assert first["default_pricing_token_events"] == 0

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT source_device, source_account, model, reasoning_effort, workspace_cwd, repository, non_cached_input_tokens FROM token_events"
        ).fetchone()
        raw_count = conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()
        malformed_count = conn.execute(
            "SELECT COUNT(*) FROM raw_events WHERE event_type IS NULL"
        ).fetchone()
    finally:
        conn.close()

    assert row == (
        "laptop-1",
        "me@example.com",
        "gpt-5.4",
        "medium",
        "C:/Progetti/personal/codex-usage",
        "codex-usage",
        80,
    )
    assert raw_count == (4,)
    assert malformed_count == (1,)


def test_import_sqlite_tracks_repository_changes_within_session(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    day_dir = sessions_dir / "2026" / "05" / "20"
    day_dir.mkdir(parents=True)
    session_file = day_dir / "rollout-repositories.jsonl"
    session_file.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-05-20T10:00:00Z","type":"turn_context","payload":{"model":"gpt-5.4","effort":"medium","cwd":"C:/Progetti/personal/codex-usage"}}',
                '{"timestamp":"2026-05-20T10:00:01Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":100,"cached_input_tokens":20,"output_tokens":10,"reasoning_output_tokens":5,"total_tokens":115}}}}',
                '{"timestamp":"2026-05-20T10:05:00Z","type":"turn_context","payload":{"model":"gpt-5.4-mini","effort":"low","cwd":"C:/Progetti/personal/other-tool/"}}',
                '{"timestamp":"2026-05-20T10:05:01Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":50,"cached_input_tokens":10,"output_tokens":8,"reasoning_output_tokens":2,"total_tokens":60}}}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    db_path = tmp_path / "usage.db"
    result = import_token_events_to_sqlite(
        db_path=db_path,
        sessions_dir=sessions_dir,
        include_archived_sessions=False,
        source_device=None,
        source_account=None,
        pricing=MODEL_PRICING_USD_PER_MILLION,
        default_pricing=MODEL_PRICING_USD_PER_MILLION["gpt-5.5"],
    )

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT model, reasoning_effort, workspace_cwd, repository, total_tokens
            FROM token_events
            ORDER BY timestamp
            """
        ).fetchall()
    finally:
        conn.close()

    assert result["inserted"] == 2
    assert rows == [
        (
            "gpt-5.4",
            "medium",
            "C:/Progetti/personal/codex-usage",
            "codex-usage",
            115,
        ),
        (
            "gpt-5.4-mini",
            "low",
            "C:/Progetti/personal/other-tool/",
            "other-tool",
            60,
        ),
    ]


def test_import_sqlite_migrates_existing_token_events_schema(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    db_path = tmp_path / "usage.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE token_events (
                event_id TEXT PRIMARY KEY,
                source_device TEXT,
                source_account TEXT,
                session_file TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                model TEXT,
                reasoning_effort TEXT,
                input_tokens INTEGER NOT NULL,
                cached_input_tokens INTEGER NOT NULL,
                non_cached_input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                reasoning_output_tokens INTEGER NOT NULL,
                total_tokens INTEGER NOT NULL,
                estimated_cost_usd REAL NOT NULL,
                raw_event_hash TEXT NOT NULL UNIQUE,
                imported_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    import_token_events_to_sqlite(
        db_path=db_path,
        sessions_dir=sessions_dir,
        include_archived_sessions=False,
        source_device=None,
        source_account=None,
        pricing=MODEL_PRICING_USD_PER_MILLION,
        default_pricing=MODEL_PRICING_USD_PER_MILLION["gpt-5.5"],
    )

    conn = sqlite3.connect(db_path)
    try:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(token_events)").fetchall()
        }
    finally:
        conn.close()

    assert "workspace_cwd" in columns
    assert "repository" in columns
    assert "pricing_used_default" in columns


def test_import_sqlite_reports_data_quality_and_duplicate_lines(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    day_dir = sessions_dir / "2026" / "05" / "20"
    day_dir.mkdir(parents=True)
    duplicate_token_line = (
        '{"timestamp":"2026-05-20T10:00:01Z","type":"event_msg",'
        '"payload":{"type":"token_count","info":{"last_token_usage":{'
        '"input_tokens":100,"cached_input_tokens":20,"output_tokens":10,'
        '"reasoning_output_tokens":5,"total_tokens":115}}}}'
    )
    session_file = day_dir / "rollout-quality.jsonl"
    session_file.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-05-20T10:00:00Z","type":"turn_context","payload":{"model":"gpt-5.4","effort":"medium","cwd":"C:/repo/project"}}',
                duplicate_token_line,
                duplicate_token_line,
                '{"timestamp":"2026-05-20T10:00:02Z","type":"event_msg","payload":{"type":"task_started"}}',
                '{"timestamp":"2026-05-20T10:00:03Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":10}}}}',
                '{"timestamp":"2026-05-20T10:00:04Z","type":"event_msg"}',
                "{bad json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = import_token_events_to_sqlite(
        db_path=tmp_path / "usage.db",
        sessions_dir=sessions_dir,
        include_archived_sessions=False,
        source_device=None,
        source_account=None,
        pricing=MODEL_PRICING_USD_PER_MILLION,
        default_pricing=MODEL_PRICING_USD_PER_MILLION["gpt-5.5"],
    )

    assert result["lines_scanned"] == 7
    assert result["raw_inserted"] == 6
    assert result["raw_skipped_duplicate"] == 1
    assert result["token_inserted"] == 1
    assert result["token_skipped_duplicate"] == 1
    assert result["malformed_json_lines"] == 1
    assert result["missing_payload_type"] == 1
    assert result["missing_token_fields"] == 1
    assert result["non_token_events"] == 2


def test_import_sqlite_marks_unknown_model_default_pricing(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    day_dir = sessions_dir / "2026" / "05" / "20"
    day_dir.mkdir(parents=True)
    session_file = day_dir / "rollout-unknown-model.jsonl"
    session_file.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-05-20T10:00:00Z","type":"turn_context","payload":{"model":"future-model","effort":"medium","cwd":"C:/repo/project"}}',
                '{"timestamp":"2026-05-20T10:00:01Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":100,"cached_input_tokens":20,"output_tokens":10,"reasoning_output_tokens":5,"total_tokens":115}}}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    db_path = tmp_path / "usage.db"
    result = import_token_events_to_sqlite(
        db_path=db_path,
        sessions_dir=sessions_dir,
        include_archived_sessions=False,
        source_device=None,
        source_account=None,
        pricing=MODEL_PRICING_USD_PER_MILLION,
        default_pricing=MODEL_PRICING_USD_PER_MILLION["gpt-5.5"],
    )

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT model, pricing_used_default FROM token_events"
        ).fetchone()
    finally:
        conn.close()

    assert result["default_pricing_token_events"] == 1
    assert row == ("future-model", 1)
