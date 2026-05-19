from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from codex_usage.models import TokenUsageEvent

REQUIRED_TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _to_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _extract_model(payload: dict[str, Any], event_payload: dict[str, Any]) -> str | None:
    info = event_payload.get("info")
    candidates = (
        event_payload.get("model"),
        payload.get("model"),
        info.get("model") if isinstance(info, dict) else None,
        payload.get("model_slug"),
    )
    for candidate in candidates:
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def parse_token_usage_event_with_status(line: str) -> tuple[str, TokenUsageEvent | None]:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return ("malformed_json", None)

    if not isinstance(payload, dict):
        return ("missing_payload_type", None)

    event_payload = payload.get("payload")
    if not isinstance(event_payload, dict):
        return ("missing_payload_type", None)
    if event_payload.get("type") != "token_count":
        return ("not_token_event", None)

    info = event_payload.get("info")
    usage: dict[str, Any] | None = None
    cumulative_usage: dict[str, Any] | None = None
    if isinstance(info, dict):
        last_usage = info.get("last_token_usage")
        total_usage = info.get("total_token_usage")
        if isinstance(last_usage, dict):
            usage = last_usage
        if isinstance(total_usage, dict):
            cumulative_usage = total_usage
        if usage is None and isinstance(total_usage, dict):
            usage = total_usage
    if usage is None:
        usage = event_payload

    if any(field not in usage for field in REQUIRED_TOKEN_FIELDS):
        return ("missing_token_fields", None)

    timestamp = (
        _parse_timestamp(payload.get("timestamp"))
        or _parse_timestamp(payload.get("created_at"))
        or _parse_timestamp(event_payload.get("timestamp"))
    )
    if timestamp is None:
        return ("missing_payload_type", None)

    return (
        "valid",
        TokenUsageEvent(
        timestamp=timestamp,
        input_tokens=_to_int(usage.get("input_tokens")),
        cached_input_tokens=_to_int(usage.get("cached_input_tokens")),
        output_tokens=_to_int(usage.get("output_tokens")),
        reasoning_output_tokens=_to_int(usage.get("reasoning_output_tokens")),
        total_tokens=_to_int(usage.get("total_tokens")),
        cumulative_total_tokens=(
            _to_int(cumulative_usage.get("total_tokens"))
            if cumulative_usage is not None
            else None
        ),
        model=_extract_model(payload, event_payload),
        ),
    )


def parse_token_usage_event(line: str) -> TokenUsageEvent | None:
    status, event = parse_token_usage_event_with_status(line)
    if status != "valid":
        return None
    return event


def iter_events_from_file(path: Path) -> Iterator[TokenUsageEvent]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            event = parse_token_usage_event(line)
            if event is not None:
                yield event
