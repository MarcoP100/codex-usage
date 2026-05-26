from __future__ import annotations

from pathlib import Path

from codex_usage.cli import cmd_summary


def test_summary_tracks_realistic_multi_turn_session(
    tmp_path: Path,
    capsys,
) -> None:
    sessions_dir = tmp_path / "sessions"
    day_dir = sessions_dir / "2026" / "05" / "20"
    day_dir.mkdir(parents=True)
    session_file = day_dir / "rollout-realistic.jsonl"
    session_file.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-05-20T10:00:00Z","type":"turn_context","payload":{"model":"gpt-5.4","effort":"medium","cwd":"C:/Progetti/personal/codex-usage"}}',
                '{"timestamp":"2026-05-20T10:00:01Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":100,"cached_input_tokens":20,"output_tokens":10,"reasoning_output_tokens":5,"total_tokens":115}}}}',
                '{"timestamp":"2026-05-20T10:00:02Z","type":"event_msg","payload":{"type":"task_started"}}',
                '{"timestamp":"2026-05-20T10:05:00Z","type":"turn_context","payload":{"model":"gpt-5.4-mini","effort":"low","cwd":"C:/Progetti/personal/other-tool"}}',
                '{"timestamp":"2026-05-20T10:05:01Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":50,"cached_input_tokens":10,"output_tokens":8,"reasoning_output_tokens":2,"total_tokens":60}}}}',
                "{bad json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = cmd_summary(
        sessions_dir=sessions_dir,
        include_archived_sessions=False,
        export_events_csv=None,
        export_daily_csv=None,
        save_report=None,
        export_model_costs_csv=None,
        export_repo_csv=None,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Files scanned: 1" in output
    assert "Valid token events: 2" in output
    assert "Malformed JSON lines: 1" in output
    assert "gpt-5.4: 115" in output
    assert "gpt-5.4-mini: 60" in output
    assert "medium: 115" in output
    assert "low: 60" in output
    assert "codex-usage: events=1" in output
    assert "other-tool: events=1" in output


def test_summary_reports_duplicate_token_events(tmp_path: Path, capsys) -> None:
    sessions_dir = tmp_path / "sessions"
    day_dir = sessions_dir / "2026" / "05" / "20"
    day_dir.mkdir(parents=True)
    duplicate_token_line = (
        '{"timestamp":"2026-05-20T10:00:01Z","type":"event_msg",'
        '"payload":{"type":"token_count","info":{"last_token_usage":{'
        '"input_tokens":100,"cached_input_tokens":20,"output_tokens":10,'
        '"reasoning_output_tokens":5,"total_tokens":115}}}}'
    )
    session_file = day_dir / "rollout-duplicates.jsonl"
    session_file.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-05-20T10:00:00Z","type":"turn_context","payload":{"model":"gpt-5.4","effort":"medium","cwd":"C:/repo/project"}}',
                duplicate_token_line,
                duplicate_token_line,
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = cmd_summary(
        sessions_dir=sessions_dir,
        include_archived_sessions=False,
        export_events_csv=None,
        export_daily_csv=None,
        save_report=None,
        export_model_costs_csv=None,
        export_repo_csv=None,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Valid token events: 1" in output
    assert "Duplicate events skipped: 1" in output


def test_summary_reports_unknown_models_using_default_pricing(
    tmp_path: Path,
    capsys,
) -> None:
    sessions_dir = tmp_path / "sessions"
    day_dir = sessions_dir / "2026" / "05" / "20"
    day_dir.mkdir(parents=True)
    session_file = day_dir / "rollout-unknown-pricing.jsonl"
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

    exit_code = cmd_summary(
        sessions_dir=sessions_dir,
        include_archived_sessions=False,
        export_events_csv=None,
        export_daily_csv=None,
        save_report=None,
        export_model_costs_csv=None,
        export_repo_csv=None,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Models using default pricing" in output
    assert "future-model: 1 event(s)" in output
