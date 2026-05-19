from __future__ import annotations

from codex_usage.parser import (
    parse_token_usage_event,
    parse_token_usage_event_with_status,
    parse_turn_context_metadata,
)
from codex_usage.report import summarize


def test_parse_token_count_event() -> None:
    line = (
        '{"timestamp":"2026-05-19T10:00:00Z","payload":{"type":"token_count","info":{'
        '"last_token_usage":{"input_tokens":100,"cached_input_tokens":20,"output_tokens":30,'
        '"reasoning_output_tokens":10,"total_tokens":160}}}}'
    )

    event = parse_token_usage_event(line)

    assert event is not None
    assert event.input_tokens == 100
    assert event.cached_input_tokens == 20
    assert event.output_tokens == 30
    assert event.reasoning_output_tokens == 10
    assert event.total_tokens == 160
    assert event.cumulative_total_tokens is None


def test_parse_ignores_non_token_count() -> None:
    line = '{"timestamp":"2026-05-19T10:00:00Z","payload":{"type":"other"}}'
    event = parse_token_usage_event(line)
    assert event is None


def test_parse_fallbacks_to_payload_fields() -> None:
    line = (
        '{"timestamp":"2026-05-19T10:00:00Z","payload":{"type":"token_count",'
        '"input_tokens":7,"cached_input_tokens":3,"output_tokens":5,'
        '"reasoning_output_tokens":2,"total_tokens":12}}'
    )
    event = parse_token_usage_event(line)
    assert event is not None
    assert event.total_tokens == 12


def test_summary_aggregates_events() -> None:
    line_a = (
        '{"timestamp":"2026-05-19T10:00:00Z","payload":{"type":"token_count","info":{'
        '"last_token_usage":{"input_tokens":10,"cached_input_tokens":1,"output_tokens":2,'
        '"reasoning_output_tokens":3,"total_tokens":16}}}}'
    )
    line_b = (
        '{"timestamp":"2026-05-19T11:00:00Z","payload":{"type":"token_count","info":{'
        '"last_token_usage":{"input_tokens":20,"cached_input_tokens":2,"output_tokens":4,'
        '"reasoning_output_tokens":6,"total_tokens":32}}}}'
    )
    events = [parse_token_usage_event(line_a), parse_token_usage_event(line_b)]
    summary = summarize([event for event in events if event is not None])

    assert summary.events == 2
    assert summary.input_tokens == 30
    assert summary.cached_input_tokens == 3
    assert summary.output_tokens == 6
    assert summary.reasoning_output_tokens == 9
    assert summary.total_tokens == 48


def test_parse_reads_cumulative_total_from_info() -> None:
    line = (
        '{"timestamp":"2026-05-19T10:00:00Z","payload":{"type":"token_count","info":{'
        '"last_token_usage":{"input_tokens":10,"cached_input_tokens":1,"output_tokens":2,'
        '"reasoning_output_tokens":3,"total_tokens":16},'
        '"total_token_usage":{"input_tokens":110,"cached_input_tokens":11,"output_tokens":22,'
        '"reasoning_output_tokens":33,"total_tokens":176}}}}'
    )
    event = parse_token_usage_event(line)
    assert event is not None
    assert event.total_tokens == 16
    assert event.cumulative_total_tokens == 176


def test_parse_with_status_malformed_json() -> None:
    status, event = parse_token_usage_event_with_status("{bad json")
    assert status == "malformed_json"
    assert event is None


def test_parse_with_status_missing_token_fields() -> None:
    line = (
        '{"timestamp":"2026-05-19T10:00:00Z","payload":{"type":"token_count","info":{'
        '"last_token_usage":{"input_tokens":10}}}}'
    )
    status, event = parse_token_usage_event_with_status(line)
    assert status == "missing_token_fields"
    assert event is None


def test_parse_turn_context_metadata() -> None:
    line = (
        '{"timestamp":"2026-05-19T10:00:00Z","type":"turn_context",'
        '"payload":{"model":"gpt-5.4","effort":"medium",'
        '"collaboration_mode":{"settings":{"reasoning_effort":"high"}}}}'
    )
    model, effort = parse_turn_context_metadata(line)
    assert model == "gpt-5.4"
    assert effort == "medium"


def test_parse_model_fallback_to_default_model_slug() -> None:
    line = (
        '{"timestamp":"2026-05-19T10:00:00Z","default_model_slug":"gpt-5.3-codex",'
        '"payload":{"type":"token_count","input_tokens":7,"cached_input_tokens":3,'
        '"output_tokens":5,"reasoning_output_tokens":2,"total_tokens":12}}'
    )
    event = parse_token_usage_event(line)
    assert event is not None
    assert event.model == "gpt-5.3-codex"
