from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class TokenUsageEvent:
    timestamp: datetime
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    total_tokens: int
    cumulative_total_tokens: int | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    workspace_cwd: str | None = None


@dataclass(frozen=True, slots=True)
class UsageSummary:
    events: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    total_tokens: int
