from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from codex_usage.models import TokenUsageEvent
from codex_usage.parser import parse_token_usage_event_with_status, parse_turn_context_metadata
from codex_usage.scanner import iter_session_files


@dataclass(slots=True)
class DataQuality:
    files_scanned: int = 0
    lines_scanned: int = 0
    malformed_json_lines: int = 0
    missing_payload_type: int = 0
    missing_token_fields: int = 0
    non_token_events: int = 0


@dataclass(frozen=True, slots=True)
class ParsedTokenEvent:
    session_file: Path
    line_number: int
    line: str
    event: TokenUsageEvent


@dataclass(frozen=True, slots=True)
class ParsedSessionLine:
    session_file: Path
    line_number: int
    line: str
    status: str
    event: TokenUsageEvent | None


def iter_session_lines(
    sessions_dir: Path,
    *,
    include_archived_sessions: bool,
    data_quality: DataQuality | None = None,
) -> Iterator[ParsedSessionLine]:
    quality = data_quality if data_quality is not None else DataQuality()

    for session_file in iter_session_files(
        sessions_dir,
        include_archived_sessions=include_archived_sessions,
    ):
        quality.files_scanned += 1
        current_model: str | None = None
        current_effort: str | None = None
        current_cwd: str | None = None

        with session_file.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                quality.lines_scanned += 1
                turn_model, turn_effort, turn_cwd = parse_turn_context_metadata(line)
                if turn_model:
                    current_model = turn_model
                if turn_effort:
                    current_effort = turn_effort
                if turn_cwd:
                    current_cwd = turn_cwd

                status, event = parse_token_usage_event_with_status(line)
                if status == "malformed_json":
                    quality.malformed_json_lines += 1
                elif status == "missing_payload_type":
                    quality.missing_payload_type += 1
                elif status == "missing_token_fields":
                    quality.missing_token_fields += 1
                elif status == "not_token_event":
                    quality.non_token_events += 1

                if status == "valid" and event is not None:
                    event = _with_turn_context(
                        event,
                        model=current_model,
                        reasoning_effort=current_effort,
                        workspace_cwd=current_cwd,
                    )

                yield ParsedSessionLine(
                    session_file=session_file,
                    line_number=line_number,
                    line=line,
                    status=status,
                    event=event,
                )


def iter_enriched_token_events(
    sessions_dir: Path,
    *,
    include_archived_sessions: bool,
    data_quality: DataQuality | None = None,
) -> Iterator[ParsedTokenEvent]:
    for parsed_line in iter_session_lines(
        sessions_dir,
        include_archived_sessions=include_archived_sessions,
        data_quality=data_quality,
    ):
        if parsed_line.status != "valid" or parsed_line.event is None:
            continue
        yield ParsedTokenEvent(
            session_file=parsed_line.session_file,
            line_number=parsed_line.line_number,
            line=parsed_line.line,
            event=parsed_line.event,
        )


def _with_turn_context(
    event: TokenUsageEvent,
    *,
    model: str | None,
    reasoning_effort: str | None,
    workspace_cwd: str | None,
) -> TokenUsageEvent:
    if (
        event.model is not None
        and event.reasoning_effort is not None
        and event.workspace_cwd is not None
    ):
        return event
    return TokenUsageEvent(
        timestamp=event.timestamp,
        input_tokens=event.input_tokens,
        cached_input_tokens=event.cached_input_tokens,
        output_tokens=event.output_tokens,
        reasoning_output_tokens=event.reasoning_output_tokens,
        total_tokens=event.total_tokens,
        cumulative_total_tokens=event.cumulative_total_tokens,
        model=event.model or model,
        reasoning_effort=event.reasoning_effort or reasoning_effort,
        workspace_cwd=event.workspace_cwd or workspace_cwd,
    )
