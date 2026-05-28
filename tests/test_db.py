from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

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
                '{"timestamp":"2026-05-20T10:00:01Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":100,"cached_input_tokens":20,"output_tokens":10,"reasoning_output_tokens":5,"total_tokens":110},"total_token_usage":{"input_tokens":1000,"cached_input_tokens":200,"output_tokens":100,"reasoning_output_tokens":50,"total_tokens":1150}}}}',
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
    assert isinstance(first["import_run_id"], str)
    assert isinstance(first["pricing_profile_id"], str)
    assert second["inserted"] == 0
    assert isinstance(second["import_run_id"], str)
    assert second["pricing_profile_id"] == first["pricing_profile_id"]
    assert second["import_run_id"] != first["import_run_id"]
    assert second["skipped_duplicate"] == 1
    assert first["raw_inserted"] == 4
    assert second["raw_inserted"] == 0
    assert first["malformed_json_lines"] == 1
    assert first["missing_payload_type"] == 0
    assert first["missing_token_fields"] == 0
    assert first["non_token_events"] == 2
    assert first["default_pricing_token_events"] == 0
    assert first["pricing_backfilled_token_events"] == 0

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT source_device, source_account, model, reasoning_effort,
                   workspace_cwd, repository, non_cached_input_tokens,
                   cumulative_total_tokens,
                   estimated_non_cached_input_cost_usd,
                   estimated_cached_input_cost_usd,
                   estimated_output_cost_usd,
                   estimated_cost_usd,
                   pricing_profile_id
            FROM token_events
            """
        ).fetchone()
        raw_count = conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()
        malformed_count = conn.execute(
            "SELECT COUNT(*) FROM raw_events WHERE event_type IS NULL"
        ).fetchone()
        import_runs = conn.execute(
            """
            SELECT import_run_id, started_at, completed_at, sessions_dir,
                   include_archived_sessions, source_device, source_account,
                   files_scanned, lines_scanned, raw_inserted, raw_skipped_duplicate,
                   token_inserted, token_skipped_duplicate, malformed_json_lines,
                   non_token_events, pricing_profile_id
            FROM import_runs
            ORDER BY completed_at
            """
        ).fetchall()
        pricing_profile = conn.execute(
            """
            SELECT pricing_profile_id, profile_name,
                   default_non_cached_input_usd_per_million,
                   default_cached_input_usd_per_million,
                   default_output_usd_per_million
            FROM pricing_profiles
            """
        ).fetchone()
        pricing_rates = conn.execute(
            """
            SELECT model, non_cached_input_usd_per_million,
                   cached_input_usd_per_million, output_usd_per_million
            FROM pricing_profile_rates
            WHERE pricing_profile_id = ?
            ORDER BY model
            """,
            (first["pricing_profile_id"],),
        ).fetchall()
    finally:
        conn.close()

    assert row[:8] == (
        "laptop-1",
        "me@example.com",
        "gpt-5.4",
        "medium",
        "C:/Progetti/personal/codex-usage",
        "codex-usage",
        80,
        1150,
    )
    assert row[8:12] == pytest.approx((0.0002, 0.000005, 0.00015, 0.000355))
    assert row[12] == first["pricing_profile_id"]
    assert raw_count == (4,)
    assert malformed_count == (1,)
    assert import_runs == [
        (
            first["import_run_id"],
            import_runs[0][1],
            import_runs[0][2],
            str(sessions_dir),
            0,
            "laptop-1",
            "me@example.com",
            1,
            4,
            4,
            0,
            1,
            0,
            1,
            2,
            first["pricing_profile_id"],
        ),
        (
            second["import_run_id"],
            import_runs[1][1],
            import_runs[1][2],
            str(sessions_dir),
            0,
            "laptop-1",
            "me@example.com",
            1,
            4,
            0,
            4,
            0,
            1,
            1,
            2,
            first["pricing_profile_id"],
        ),
    ]
    assert import_runs[0][1]
    assert import_runs[0][2]
    assert import_runs[1][1]
    assert import_runs[1][2]
    assert pricing_profile == (
        first["pricing_profile_id"],
        "builtin",
        5.0,
        0.5,
        30.0,
    )
    assert pricing_rates == [
        ("gpt-5.3-codex", 1.75, 0.175, 14.0),
        ("gpt-5.4", 2.5, 0.25, 15.0),
        ("gpt-5.4-mini", 0.75, 0.075, 4.5),
        ("gpt-5.5", 5.0, 0.5, 30.0),
    ]


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
        repo_rows = conn.execute(
            """
            SELECT repository, events, input_tokens, cached_input_tokens,
                   non_cached_input_tokens, output_tokens, total_tokens,
                   estimated_cost_usd
            FROM repositories
            ORDER BY repository
            """
        ).fetchall()
        daily_row = conn.execute(
            """
            SELECT usage_date, events, input_tokens, cached_input_tokens,
                   non_cached_input_tokens, output_tokens, total_tokens,
                   estimated_cost_usd
            FROM daily_usage
            """
        ).fetchone()
        weekly_row = conn.execute(
            """
            SELECT usage_week, events, total_tokens, estimated_cost_usd
            FROM weekly_usage
            """
        ).fetchone()
        monthly_row = conn.execute(
            """
            SELECT usage_month, events, total_tokens, estimated_cost_usd
            FROM monthly_usage
            """
        ).fetchone()
        model_rows = conn.execute(
            """
            SELECT model, events, total_tokens, estimated_cost_usd
            FROM model_usage
            ORDER BY model
            """
        ).fetchall()
        model_effort_rows = conn.execute(
            """
            SELECT model, reasoning_effort, events, total_tokens
            FROM model_effort_usage
            ORDER BY model
            """
        ).fetchall()
        repository_usage_rows = conn.execute(
            """
            SELECT repository, events, total_tokens, estimated_cost_usd
            FROM repository_usage
            ORDER BY repository
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
    assert [row[:7] for row in repo_rows] == [
        ("codex-usage", 1, 100, 20, 80, 10, 115),
        ("other-tool", 1, 50, 10, 40, 8, 60),
    ]
    assert [row[7] for row in repo_rows] == pytest.approx([0.000355, 0.00006675])
    assert daily_row[:7] == ("2026-05-20", 2, 150, 30, 120, 18, 175)
    assert daily_row[7] == pytest.approx(0.00042175)
    assert weekly_row[0].startswith("2026-W")
    assert weekly_row[1:3] == (2, 175)
    assert weekly_row[3] == pytest.approx(0.00042175)
    assert monthly_row[:3] == ("2026-05", 2, 175)
    assert monthly_row[3] == pytest.approx(0.00042175)
    assert [row[:3] for row in model_rows] == [
        ("gpt-5.4", 1, 115),
        ("gpt-5.4-mini", 1, 60),
    ]
    assert [row[3] for row in model_rows] == pytest.approx([0.000355, 0.00006675])
    assert model_effort_rows == [
        ("gpt-5.4", "medium", 1, 115),
        ("gpt-5.4-mini", "low", 1, 60),
    ]
    assert [row[:3] for row in repository_usage_rows] == [
        ("codex-usage", 1, 115),
        ("other-tool", 1, 60),
    ]
    assert [row[3] for row in repository_usage_rows] == pytest.approx(
        [0.000355, 0.00006675]
    )


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
        views = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'view'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert "workspace_cwd" in columns
    assert "repository" in columns
    assert "pricing_used_default" in columns
    assert "cumulative_total_tokens" in columns
    assert "estimated_non_cached_input_cost_usd" in columns
    assert "estimated_cached_input_cost_usd" in columns
    assert "estimated_output_cost_usd" in columns
    assert "pricing_profile_id" in columns
    assert {
        "daily_usage",
        "model_effort_usage",
        "model_usage",
        "monthly_usage",
        "repositories",
        "repository_usage",
        "weekly_usage",
    }.issubset(views)
    conn = sqlite3.connect(db_path)
    try:
        import_runs_count = conn.execute("SELECT COUNT(*) FROM import_runs").fetchone()
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        conn.close()
    assert import_runs_count == (1,)
    assert {"pricing_profiles", "pricing_profile_rates"}.issubset(tables)


def test_import_sqlite_backfills_pricing_for_existing_token_events(tmp_path: Path) -> None:
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
        conn.execute(
            """
            INSERT INTO token_events (
                event_id, source_device, source_account, session_file, timestamp,
                model, reasoning_effort, input_tokens, cached_input_tokens,
                non_cached_input_tokens, output_tokens, reasoning_output_tokens,
                total_tokens, estimated_cost_usd, raw_event_hash, imported_at
            ) VALUES (
                'event-1', NULL, NULL, 'session.jsonl', '2026-05-20T10:00:01+00:00',
                'gpt-5.4', 'medium', 100, 20, 80, 10, 5,
                115, 0.000355, 'hash-1', '2026-05-20T10:00:02+00:00'
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

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
            """
            SELECT estimated_non_cached_input_cost_usd,
                   estimated_cached_input_cost_usd,
                   estimated_output_cost_usd,
                   pricing_profile_id
            FROM token_events
            """
        ).fetchone()
    finally:
        conn.close()

    assert result["pricing_backfilled_token_events"] == 1
    assert row[:3] == pytest.approx((0.0002, 0.000005, 0.00015))
    assert row[3] == result["pricing_profile_id"]


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
