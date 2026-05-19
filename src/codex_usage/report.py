from __future__ import annotations

from collections.abc import Iterable

from codex_usage.models import TokenUsageEvent, UsageSummary


def summarize(events: Iterable[TokenUsageEvent]) -> UsageSummary:
    event_list = list(events)
    return UsageSummary(
        events=len(event_list),
        input_tokens=sum(e.input_tokens for e in event_list),
        cached_input_tokens=sum(e.cached_input_tokens for e in event_list),
        output_tokens=sum(e.output_tokens for e in event_list),
        reasoning_output_tokens=sum(e.reasoning_output_tokens for e in event_list),
        total_tokens=sum(e.total_tokens for e in event_list),
    )
