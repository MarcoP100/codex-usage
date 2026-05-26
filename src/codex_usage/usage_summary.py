from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from codex_usage.ingestion import DataQuality, iter_enriched_token_events
from codex_usage.models import TokenUsageEvent, UsageSummary
from codex_usage.pricing import cost_breakdown_usd
from codex_usage.repository import repository_key_from_cwd
from codex_usage.report import summarize


@dataclass(slots=True)
class UsageSummaryData:
    events: list[TokenUsageEvent] = field(default_factory=list)
    data_quality: DataQuality = field(default_factory=DataQuality)
    duplicate_events_skipped: int = 0
    session_final_cumulative_total: int = 0
    daily_total_tokens: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    daily_cached_tokens: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    daily_input_tokens: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    daily_output_tokens: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    daily_events: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    model_total_tokens: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    effort_total_tokens: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    model_effort_total_tokens: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    daily_estimated_cost: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    daily_non_cached_input_cost: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    daily_cached_input_cost: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    daily_output_cost: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    model_estimated_cost: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    model_non_cached_input_cost: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    model_cached_input_cost: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    model_output_cost: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    repo_events: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    repo_input_tokens: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    repo_cached_tokens: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    repo_output_tokens: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    repo_non_cached_cost: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    repo_cached_cost: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    repo_output_cost: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    repo_total_cost: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    @property
    def summary(self) -> UsageSummary:
        return summarize(self.events)

    @property
    def non_cached_input(self) -> int:
        summary = self.summary
        return summary.input_tokens - summary.cached_input_tokens

    @property
    def effective_new_tokens(self) -> int:
        summary = self.summary
        return self.non_cached_input + summary.output_tokens + summary.reasoning_output_tokens

    @property
    def average_tokens_per_event(self) -> float:
        summary = self.summary
        return summary.total_tokens / summary.events if summary.events else 0.0

    @property
    def median_tokens_per_event(self) -> float:
        return statistics.median(event.total_tokens for event in self.events) if self.events else 0.0

    @property
    def top_heaviest_events(self) -> list[TokenUsageEvent]:
        return sorted(self.events, key=lambda event: event.total_tokens, reverse=True)[:10]

    @property
    def estimated_total_cost(self) -> float:
        return sum(
            cost_breakdown_usd(
                model=event.model,
                input_tokens=event.input_tokens,
                cached_input_tokens=event.cached_input_tokens,
                output_tokens=event.output_tokens,
            ).total_usd
            for event in self.events
        )


def build_usage_summary_data(
    sessions_dir: Path,
    *,
    include_archived_sessions: bool,
) -> UsageSummaryData:
    data = UsageSummaryData()
    dedupe_seen: set[tuple[str, int, int, int]] = set()
    events_by_file: dict[Path, list[TokenUsageEvent]] = defaultdict(list)

    for parsed_event in iter_enriched_token_events(
        sessions_dir,
        include_archived_sessions=include_archived_sessions,
        data_quality=data.data_quality,
    ):
        event = parsed_event.event
        dedupe_key = (
            event.timestamp.isoformat(),
            event.total_tokens,
            event.input_tokens,
            event.output_tokens,
        )
        if dedupe_key in dedupe_seen:
            data.duplicate_events_skipped += 1
            continue
        dedupe_seen.add(dedupe_key)
        data.events.append(event)
        events_by_file[parsed_event.session_file].append(event)
        _add_event(data, event)

    for file_events in events_by_file.values():
        cumulative_totals = [
            event.cumulative_total_tokens
            for event in file_events
            if event.cumulative_total_tokens is not None
        ]
        if cumulative_totals:
            data.session_final_cumulative_total += cumulative_totals[-1]

    return data


def _add_event(data: UsageSummaryData, event: TokenUsageEvent) -> None:
    day = event.timestamp.date().isoformat()
    data.daily_total_tokens[day] += event.total_tokens
    data.daily_cached_tokens[day] += event.cached_input_tokens
    data.daily_input_tokens[day] += event.input_tokens
    data.daily_output_tokens[day] += event.output_tokens
    data.daily_events[day] += 1
    data.model_total_tokens[event.model or "unknown"] += event.total_tokens
    data.effort_total_tokens[event.reasoning_effort or "unknown"] += event.total_tokens
    model_effort_key = f"{event.model or 'unknown'} | {event.reasoning_effort or 'unknown'}"
    data.model_effort_total_tokens[model_effort_key] += event.total_tokens

    cost = cost_breakdown_usd(
        model=event.model,
        input_tokens=event.input_tokens,
        cached_input_tokens=event.cached_input_tokens,
        output_tokens=event.output_tokens,
    )
    data.daily_estimated_cost[day] += cost.total_usd
    data.daily_non_cached_input_cost[day] += cost.non_cached_input_usd
    data.daily_cached_input_cost[day] += cost.cached_input_usd
    data.daily_output_cost[day] += cost.output_usd

    model_key = event.model or "unknown"
    data.model_estimated_cost[model_key] += cost.total_usd
    data.model_non_cached_input_cost[model_key] += cost.non_cached_input_usd
    data.model_cached_input_cost[model_key] += cost.cached_input_usd
    data.model_output_cost[model_key] += cost.output_usd

    repo_key = repository_key_from_cwd(event.workspace_cwd)
    data.repo_events[repo_key] += 1
    data.repo_input_tokens[repo_key] += event.input_tokens
    data.repo_cached_tokens[repo_key] += event.cached_input_tokens
    data.repo_output_tokens[repo_key] += event.output_tokens
    data.repo_non_cached_cost[repo_key] += cost.non_cached_input_usd
    data.repo_cached_cost[repo_key] += cost.cached_input_usd
    data.repo_output_cost[repo_key] += cost.output_usd
    data.repo_total_cost[repo_key] += cost.total_usd
