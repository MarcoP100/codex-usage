from __future__ import annotations

from pathlib import Path

from codex_usage.db import import_token_events_to_sqlite
from codex_usage.web.view_models import build_dashboard_context, build_filter_state


MODEL_PRICING_USD_PER_MILLION = {
    "gpt-5.5": (5.0, 0.5, 30.0),
    "gpt-5.4": (2.5, 0.25, 15.0),
}


def test_build_filter_state_accepts_blank_values() -> None:
    filters, form_values, error = build_filter_state(
        {
            "from": "2026-05-01",
            "to": "",
            "repository": " codex-usage ",
            "model": "",
        }
    )

    assert error is None
    assert filters is not None
    assert filters.from_date == "2026-05-01"
    assert filters.to_date is None
    assert filters.repository == "codex-usage"
    assert filters.model is None
    assert form_values["repository"] == " codex-usage "


def test_build_filter_state_returns_validation_error() -> None:
    filters, form_values, error = build_filter_state({"from": "2026/05/01"})

    assert filters is None
    assert form_values["from"] == "2026/05/01"
    assert error == "--from must use YYYY-MM-DD format"


def test_build_dashboard_context_formats_report_for_templates(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    day_dir = sessions_dir / "2026" / "05" / "20"
    day_dir.mkdir(parents=True)
    session_file = day_dir / "rollout-view-model.jsonl"
    session_file.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-05-20T10:00:00Z","type":"turn_context","payload":{"model":"gpt-5.4","effort":"medium","cwd":"C:/repo/view-model"}}',
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
    filters, _, error = build_filter_state({})

    assert filters is not None
    assert error is None
    context = build_dashboard_context(db_path, filters)

    report = context["report"]
    assert context["report_error"] is None
    assert report["period"] == "2026-05-20T10:00:01+00:00 -> 2026-05-20T10:00:01+00:00"
    assert ("Total tokens", "115") in report["totals"]
    assert report["top_repositories"][0]["key"] == "view-model"
    assert report["charts"]["daily"][0]["label"] == "2026-05-20"
    assert report["charts"]["daily"][0]["width"] == "100"
    assert report["data_quality"]["latest"]["token_inserted"] == "1"
    assert report["data_quality"]["latest"]["raw_inserted"] == "2"
