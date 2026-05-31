from __future__ import annotations

from pathlib import Path

from codex_usage.cli import cmd_report_sqlite
from codex_usage.db import import_token_events_to_sqlite
from codex_usage.sqlite_report import SqliteUsageReportFilters, build_sqlite_usage_report


MODEL_PRICING_USD_PER_MILLION = {
    "gpt-5.5": (5.0, 0.5, 30.0),
    "gpt-5.4": (2.5, 0.25, 15.0),
    "gpt-5.4-mini": (0.75, 0.075, 4.5),
    "gpt-5.3-codex": (1.75, 0.175, 14.0),
}


def test_report_sqlite_reads_imported_usage(tmp_path: Path, capsys) -> None:
    sessions_dir = tmp_path / "sessions"
    day_dir = sessions_dir / "2026" / "05" / "20"
    day_dir.mkdir(parents=True)
    session_file = day_dir / "rollout-report.jsonl"
    session_file.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-05-20T10:00:00Z","type":"turn_context","payload":{"model":"gpt-5.4","effort":"medium","cwd":"C:/Progetti/personal/codex-usage"}}',
                '{"timestamp":"2026-05-20T10:00:01Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":100,"cached_input_tokens":20,"output_tokens":10,"reasoning_output_tokens":5,"total_tokens":115}}}}',
                '{"timestamp":"2026-05-20T10:05:00Z","type":"turn_context","payload":{"model":"gpt-5.4-mini","effort":"low","cwd":"C:/Progetti/personal/other-tool"}}',
                '{"timestamp":"2026-05-20T10:05:01Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":50,"cached_input_tokens":10,"output_tokens":8,"reasoning_output_tokens":2,"total_tokens":60}}}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "usage.db"
    report_path = tmp_path / "report.txt"
    markdown_path = tmp_path / "report.md"

    import_token_events_to_sqlite(
        db_path=db_path,
        sessions_dir=sessions_dir,
        include_archived_sessions=False,
        source_device=None,
        source_account=None,
        pricing=MODEL_PRICING_USD_PER_MILLION,
        default_pricing=MODEL_PRICING_USD_PER_MILLION["gpt-5.5"],
    )

    exit_code = cmd_report_sqlite(
        db_path=db_path,
        save_report=report_path,
        save_markdown=markdown_path,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "SQLite DB:" in output
    assert "Events:                  2" in output
    assert "Usage tokens estimate:   175" in output
    assert "Cache ratio:             20.0%" in output
    assert "codex-usage: events=1" in output
    assert "other-tool: events=1" in output
    assert "gpt-5.4: events=1" in output
    assert "gpt-5.4-mini: events=1" in output
    assert "Top days" in output
    assert "Top sessions" in output
    assert "Top events" in output
    assert "rollout-report.jsonl: events=2" in output
    assert "2026-05-20T10:00:01+00:00 | codex-usage | gpt-5.4" in output
    assert "2026-05: events=2" in output
    assert "2026-05-20: events=2" in output
    assert report_path.read_text(encoding="utf-8") == output
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# Codex Usage Report" in markdown
    assert "## Token Totals" in markdown
    assert "| Metric | Value |" in markdown
    assert "## Top Repositories" in markdown
    assert "| codex-usage | 1 | 115" in markdown
    assert "## Top Events" in markdown


def test_report_sqlite_filters_by_period_repository_and_model(
    tmp_path: Path,
    capsys,
) -> None:
    sessions_dir = tmp_path / "sessions"
    day_dir = sessions_dir / "2026" / "05" / "20"
    day_dir.mkdir(parents=True)
    session_file = day_dir / "rollout-filtered-report.jsonl"
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

    exit_code = cmd_report_sqlite(
        db_path=db_path,
        save_report=None,
        filters=SqliteUsageReportFilters(
            from_date="2026-05-20",
            to_date="2026-05-20",
            repository="keep",
            model="gpt-5.4",
        ),
        group_by="day",
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Filters: from=2026-05-20, to=2026-05-20, repository=keep, model=gpt-5.4" in output
    assert "Events:                  1" in output
    assert "Usage tokens estimate:   115" in output
    assert "keep: events=1" in output
    assert "gpt-5.4: events=1" in output
    assert "Usage by day" in output
    assert "2026-05-20: events=1" in output
    assert "drop: events=1" not in output
    assert "gpt-5.4-mini: events=1" not in output


def test_report_sqlite_rejects_invalid_date_filter() -> None:
    try:
        SqliteUsageReportFilters(from_date="2026/05/20")
    except ValueError as exc:
        assert "--from must use YYYY-MM-DD format" in str(exc)
    else:
        raise AssertionError("invalid date filter was accepted")


def test_report_sqlite_groups_by_week(tmp_path: Path, capsys) -> None:
    sessions_dir = tmp_path / "sessions"
    day_dir = sessions_dir / "2026" / "05" / "20"
    day_dir.mkdir(parents=True)
    session_file = day_dir / "rollout-weekly-report.jsonl"
    session_file.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-05-20T10:00:00Z","type":"turn_context","payload":{"model":"gpt-5.4","effort":"medium","cwd":"C:/repo/project"}}',
                '{"timestamp":"2026-05-20T10:00:01Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":100,"cached_input_tokens":20,"output_tokens":10,"reasoning_output_tokens":5,"total_tokens":115}}}}',
                '{"timestamp":"2026-05-21T10:00:01Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":50,"cached_input_tokens":10,"output_tokens":8,"reasoning_output_tokens":2,"total_tokens":60}}}}',
                '{"timestamp":"2026-05-28T10:00:01Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":70,"cached_input_tokens":7,"output_tokens":9,"reasoning_output_tokens":3,"total_tokens":82}}}}',
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

    exit_code = cmd_report_sqlite(
        db_path=db_path,
        save_report=None,
        group_by="week",
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Usage by week" in output
    assert "events=2 tokens=175" in output
    assert "events=1 tokens=82" in output


def test_report_sqlite_rejects_invalid_group_by(tmp_path: Path) -> None:
    try:
        build_sqlite_usage_report(tmp_path / "usage.db", group_by="quarter")
    except ValueError as exc:
        assert "--group-by must be one of: day, week, month" in str(exc)
    else:
        raise AssertionError("invalid group-by was accepted")
