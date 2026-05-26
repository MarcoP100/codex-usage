from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path

from codex_usage.config import load_app_config
from codex_usage.db import import_token_events_to_sqlite
from codex_usage.parser import parse_token_usage_event_with_status, parse_turn_context_metadata
from codex_usage.repository import repository_key_from_cwd
from codex_usage.report import summarize
from codex_usage.scanner import iter_session_files

MODEL_PRICING_USD_PER_MILLION: dict[str, tuple[float, float, float]] = {
    "gpt-5.5": (5.0, 0.5, 30.0),
    "gpt-5.4": (2.5, 0.25, 15.0),
    "gpt-5.4-mini": (0.75, 0.075, 4.5),
    "gpt-5.3-codex": (1.75, 0.175, 14.0),
}
DEFAULT_PRICING_USD_PER_MILLION = MODEL_PRICING_USD_PER_MILLION["gpt-5.5"]


def _human_tokens(value: int) -> str:
    abs_value = abs(value)
    if abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs_value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def _fmt_tokens(value: int) -> str:
    return f"{value:,} ({_human_tokens(value)})"


def _fmt_pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "n/a"
    return f"{(numerator / denominator) * 100:.1f}%"


def _usd_from_million_tokens(tokens: int, usd_per_million: float) -> float:
    return (tokens / 1_000_000) * usd_per_million


def _fmt_usd(value: float) -> str:
    return f"${value:,.1f}"


def _day_key(value) -> str:
    return value.date().isoformat()


def _estimated_cost_usd(
    model: str | None,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
) -> float:
    return sum(_cost_components_usd(model, input_tokens, cached_input_tokens, output_tokens))


def _cost_components_usd(
    model: str | None,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
) -> tuple[float, float, float]:
    model_key = (model or "").strip().lower()
    non_cached_rate, cached_rate, output_rate = MODEL_PRICING_USD_PER_MILLION.get(
        model_key, DEFAULT_PRICING_USD_PER_MILLION
    )
    non_cached_input = input_tokens - cached_input_tokens
    non_cached_input_cost = _usd_from_million_tokens(
        non_cached_input, non_cached_rate
    )
    cached_input_cost = _usd_from_million_tokens(
        cached_input_tokens, cached_rate
    )
    output_cost = _usd_from_million_tokens(output_tokens, output_rate)
    return (non_cached_input_cost, cached_input_cost, output_cost)


def _write_events_csv(path: Path, events) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "timestamp",
                "model",
                "input_tokens",
                "cached_input_tokens",
                "output_tokens",
                "reasoning_tokens",
                "total_tokens",
                "estimated_non_cached_input_cost",
                "estimated_cached_input_cost",
                "estimated_output_cost",
                "estimated_cost",
                "reasoning_effort",
            ]
        )
        for event in events:
            non_cached_cost, cached_cost, output_cost = _cost_components_usd(
                event.model,
                event.input_tokens,
                event.cached_input_tokens,
                event.output_tokens,
            )
            writer.writerow(
                [
                    event.timestamp.isoformat(),
                    event.model or "unknown",
                    event.input_tokens,
                    event.cached_input_tokens,
                    event.output_tokens,
                    event.reasoning_output_tokens,
                    event.total_tokens,
                    f"{non_cached_cost:.6f}",
                    f"{cached_cost:.6f}",
                    f"{output_cost:.6f}",
                    f"{(non_cached_cost + cached_cost + output_cost):.6f}",
                    event.reasoning_effort or "unknown",
                ]
            )


def _write_daily_csv(
    path: Path,
    daily_events: dict[str, int],
    daily_input_tokens: dict[str, int],
    daily_cached_tokens: dict[str, int],
    daily_output_tokens: dict[str, int],
    daily_non_cached_input_cost: dict[str, float],
    daily_cached_input_cost: dict[str, float],
    daily_output_cost: dict[str, float],
    daily_estimated_cost: dict[str, float],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "date",
                "events",
                "input_tokens",
                "non_cached_tokens",
                "output_tokens",
                "cache_ratio",
                "estimated_non_cached_input_cost",
                "estimated_cached_input_cost",
                "estimated_output_cost",
                "estimated_cost",
            ]
        )
        for day in sorted(daily_events):
            input_tokens = daily_input_tokens[day]
            cached_tokens = daily_cached_tokens[day]
            non_cached = input_tokens - cached_tokens
            cache_ratio = (
                f"{(cached_tokens / input_tokens) * 100:.1f}" if input_tokens else "0.0"
            )
            writer.writerow(
                [
                    day,
                    daily_events[day],
                    input_tokens,
                    non_cached,
                    daily_output_tokens[day],
                    cache_ratio,
                    f"{daily_non_cached_input_cost[day]:.6f}",
                    f"{daily_cached_input_cost[day]:.6f}",
                    f"{daily_output_cost[day]:.6f}",
                    f"{daily_estimated_cost[day]:.6f}",
                ]
            )


def _write_model_costs_csv(
    path: Path,
    model_non_cached_input_cost: dict[str, float],
    model_cached_input_cost: dict[str, float],
    model_output_cost: dict[str, float],
    model_estimated_cost: dict[str, float],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "model",
                "estimated_non_cached_input_cost",
                "estimated_cached_input_cost",
                "estimated_output_cost",
                "estimated_cost",
            ]
        )
        for model in sorted(
            model_estimated_cost,
            key=lambda item: model_estimated_cost[item],
            reverse=True,
        ):
            writer.writerow(
                [
                    model,
                    f"{model_non_cached_input_cost[model]:.6f}",
                    f"{model_cached_input_cost[model]:.6f}",
                    f"{model_output_cost[model]:.6f}",
                    f"{model_estimated_cost[model]:.6f}",
                ]
            )


def _write_repo_csv(
    path: Path,
    repo_events: dict[str, int],
    repo_input_tokens: dict[str, int],
    repo_cached_tokens: dict[str, int],
    repo_output_tokens: dict[str, int],
    repo_non_cached_cost: dict[str, float],
    repo_cached_cost: dict[str, float],
    repo_output_cost: dict[str, float],
    repo_total_cost: dict[str, float],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "repository",
                "events",
                "input_tokens",
                "cached_input_tokens",
                "non_cached_input_tokens",
                "output_tokens",
                "estimated_non_cached_input_cost",
                "estimated_cached_input_cost",
                "estimated_output_cost",
                "estimated_cost",
            ]
        )
        for repo in sorted(
            repo_events,
            key=lambda item: repo_total_cost[item],
            reverse=True,
        ):
            input_tokens = repo_input_tokens[repo]
            cached_tokens = repo_cached_tokens[repo]
            writer.writerow(
                [
                    repo,
                    repo_events[repo],
                    input_tokens,
                    cached_tokens,
                    input_tokens - cached_tokens,
                    repo_output_tokens[repo],
                    f"{repo_non_cached_cost[repo]:.6f}",
                    f"{repo_cached_cost[repo]:.6f}",
                    f"{repo_output_cost[repo]:.6f}",
                    f"{repo_total_cost[repo]:.6f}",
                ]
            )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex-usage")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Optional TOML config path (default: ./config.toml if present)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    summary_parser = subparsers.add_parser("summary", help="Show token usage summary")
    summary_parser.add_argument(
        "--sessions-dir",
        type=Path,
        default=None,
        help="Base directory containing .jsonl Codex session files",
    )
    summary_parser.add_argument(
        "--include-archived-sessions",
        action="store_true",
        help="Include .jsonl files from sibling archived_sessions directory",
    )
    summary_parser.add_argument(
        "--export-events-csv",
        type=Path,
        help="Write one row per event to this CSV file",
    )
    summary_parser.add_argument(
        "--export-daily-csv",
        type=Path,
        help="Write daily summary to this CSV file",
    )
    summary_parser.add_argument(
        "--save-report",
        type=Path,
        help="Save console-style summary report to this text file",
    )
    summary_parser.add_argument(
        "--export-model-costs-csv",
        type=Path,
        help="Write estimated costs by model to this CSV file",
    )
    summary_parser.add_argument(
        "--export-repo-csv",
        type=Path,
        help="Write usage and estimated costs aggregated by repository to this CSV file",
    )

    import_parser = subparsers.add_parser(
        "import-sqlite",
        help="Import token events into a stable SQLite schema (idempotent)",
    )
    import_parser.add_argument(
        "--sessions-dir",
        type=Path,
        default=None,
        help="Base directory containing .jsonl Codex session files",
    )
    import_parser.add_argument(
        "--include-archived-sessions",
        action="store_true",
        help="Include .jsonl files from sibling archived_sessions directory",
    )
    import_parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="Target SQLite database path",
    )
    import_parser.add_argument(
        "--source-device",
        type=str,
        help="Optional source device label",
    )
    import_parser.add_argument(
        "--source-account",
        type=str,
        help="Optional source account label",
    )
    return parser


def cmd_summary(
    sessions_dir: Path,
    include_archived_sessions: bool,
    export_events_csv: Path | None,
    export_daily_csv: Path | None,
    save_report: Path | None,
    export_model_costs_csv: Path | None,
    export_repo_csv: Path | None,
) -> int:
    events = []
    files_scanned = 0
    lines_scanned = 0
    malformed_json_lines = 0
    missing_payload_type = 0
    missing_token_fields = 0
    duplicate_events_skipped = 0
    session_final_cumulative_total = 0
    dedupe_seen: set[tuple[str, int, int, int]] = set()
    daily_total_tokens: dict[str, int] = defaultdict(int)
    daily_cached_tokens: dict[str, int] = defaultdict(int)
    daily_input_tokens: dict[str, int] = defaultdict(int)
    daily_output_tokens: dict[str, int] = defaultdict(int)
    daily_events: dict[str, int] = defaultdict(int)
    model_total_tokens: dict[str, int] = defaultdict(int)
    effort_total_tokens: dict[str, int] = defaultdict(int)
    model_effort_total_tokens: dict[str, int] = defaultdict(int)
    daily_estimated_cost: dict[str, float] = defaultdict(float)
    daily_non_cached_input_cost: dict[str, float] = defaultdict(float)
    daily_cached_input_cost: dict[str, float] = defaultdict(float)
    daily_output_cost: dict[str, float] = defaultdict(float)
    model_estimated_cost: dict[str, float] = defaultdict(float)
    model_non_cached_input_cost: dict[str, float] = defaultdict(float)
    model_cached_input_cost: dict[str, float] = defaultdict(float)
    model_output_cost: dict[str, float] = defaultdict(float)
    repo_events: dict[str, int] = defaultdict(int)
    repo_input_tokens: dict[str, int] = defaultdict(int)
    repo_cached_tokens: dict[str, int] = defaultdict(int)
    repo_output_tokens: dict[str, int] = defaultdict(int)
    repo_non_cached_cost: dict[str, float] = defaultdict(float)
    repo_cached_cost: dict[str, float] = defaultdict(float)
    repo_output_cost: dict[str, float] = defaultdict(float)
    repo_total_cost: dict[str, float] = defaultdict(float)

    for jsonl_path in iter_session_files(
        sessions_dir,
        include_archived_sessions=include_archived_sessions,
    ):
        files_scanned += 1
        file_events = []
        current_model: str | None = None
        current_effort: str | None = None
        current_cwd: str | None = None
        with jsonl_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                lines_scanned += 1
                turn_model, turn_effort, turn_cwd = parse_turn_context_metadata(line)
                if turn_model:
                    current_model = turn_model
                if turn_effort:
                    current_effort = turn_effort
                if turn_cwd:
                    current_cwd = turn_cwd
                status, event = parse_token_usage_event_with_status(line)
                if status == "malformed_json":
                    malformed_json_lines += 1
                    continue
                if status == "missing_payload_type":
                    missing_payload_type += 1
                    continue
                if status == "missing_token_fields":
                    missing_token_fields += 1
                    continue
                if status != "valid" or event is None:
                    continue
                if (event.model is None and current_model is not None) or (
                    event.reasoning_effort is None and current_effort is not None
                ) or (event.workspace_cwd is None and current_cwd is not None):
                    event = event.__class__(
                        timestamp=event.timestamp,
                        input_tokens=event.input_tokens,
                        cached_input_tokens=event.cached_input_tokens,
                        output_tokens=event.output_tokens,
                        reasoning_output_tokens=event.reasoning_output_tokens,
                        total_tokens=event.total_tokens,
                        cumulative_total_tokens=event.cumulative_total_tokens,
                        model=event.model or current_model,
                        reasoning_effort=event.reasoning_effort or current_effort,
                        workspace_cwd=event.workspace_cwd or current_cwd,
                    )
                elif event.workspace_cwd is None and current_cwd is not None:
                    event = event.__class__(
                        timestamp=event.timestamp,
                        input_tokens=event.input_tokens,
                        cached_input_tokens=event.cached_input_tokens,
                        output_tokens=event.output_tokens,
                        reasoning_output_tokens=event.reasoning_output_tokens,
                        total_tokens=event.total_tokens,
                        cumulative_total_tokens=event.cumulative_total_tokens,
                        model=event.model,
                        reasoning_effort=event.reasoning_effort,
                        workspace_cwd=current_cwd,
                    )
                dedupe_key = (
                    event.timestamp.isoformat(),
                    event.total_tokens,
                    event.input_tokens,
                    event.output_tokens,
                )
                if dedupe_key in dedupe_seen:
                    duplicate_events_skipped += 1
                    continue
                dedupe_seen.add(dedupe_key)
                file_events.append(event)

        events.extend(file_events)
        file_cumulative_totals = [
            e.cumulative_total_tokens
            for e in file_events
            if e.cumulative_total_tokens is not None
        ]
        if file_cumulative_totals:
            session_final_cumulative_total += file_cumulative_totals[-1]
        for event in file_events:
            day = _day_key(event.timestamp)
            daily_total_tokens[day] += event.total_tokens
            daily_cached_tokens[day] += event.cached_input_tokens
            daily_input_tokens[day] += event.input_tokens
            daily_output_tokens[day] += event.output_tokens
            daily_events[day] += 1
            model_total_tokens[event.model or "unknown"] += event.total_tokens
            effort_total_tokens[event.reasoning_effort or "unknown"] += event.total_tokens
            model_effort_key = f"{event.model or 'unknown'} | {event.reasoning_effort or 'unknown'}"
            model_effort_total_tokens[model_effort_key] += event.total_tokens
            non_cached_cost, cached_cost, output_cost = _cost_components_usd(
                event.model,
                event.input_tokens,
                event.cached_input_tokens,
                event.output_tokens,
            )
            event_estimated_cost = non_cached_cost + cached_cost + output_cost
            daily_estimated_cost[day] += event_estimated_cost
            daily_non_cached_input_cost[day] += non_cached_cost
            daily_cached_input_cost[day] += cached_cost
            daily_output_cost[day] += output_cost
            model_key = event.model or "unknown"
            model_estimated_cost[event.model or "unknown"] += event_estimated_cost
            model_non_cached_input_cost[model_key] += non_cached_cost
            model_cached_input_cost[model_key] += cached_cost
            model_output_cost[model_key] += output_cost
            repo_key = repository_key_from_cwd(event.workspace_cwd)
            repo_events[repo_key] += 1
            repo_input_tokens[repo_key] += event.input_tokens
            repo_cached_tokens[repo_key] += event.cached_input_tokens
            repo_output_tokens[repo_key] += event.output_tokens
            repo_non_cached_cost[repo_key] += non_cached_cost
            repo_cached_cost[repo_key] += cached_cost
            repo_output_cost[repo_key] += output_cost
            repo_total_cost[repo_key] += event_estimated_cost

    summary = summarize(events)
    non_cached_input = summary.input_tokens - summary.cached_input_tokens
    effective_new_tokens = (
        non_cached_input + summary.output_tokens + summary.reasoning_output_tokens
    )
    avg_tokens_per_event = (
        summary.total_tokens / summary.events if summary.events else 0.0
    )
    median_tokens_per_event = (
        statistics.median(event.total_tokens for event in events) if events else 0.0
    )
    top_heaviest_events = sorted(events, key=lambda event: event.total_tokens, reverse=True)[:10]
    estimated_total_cost = sum(
        _estimated_cost_usd(
            event.model,
            event.input_tokens,
            event.cached_input_tokens,
            event.output_tokens,
        )
        for event in events
    )

    if export_events_csv is not None:
        _write_events_csv(export_events_csv, events)
    if export_daily_csv is not None:
        _write_daily_csv(
            export_daily_csv,
            daily_events,
            daily_input_tokens,
            daily_cached_tokens,
            daily_output_tokens,
            daily_non_cached_input_cost,
            daily_cached_input_cost,
            daily_output_cost,
            daily_estimated_cost,
        )
    if export_model_costs_csv is not None:
        _write_model_costs_csv(
            export_model_costs_csv,
            model_non_cached_input_cost,
            model_cached_input_cost,
            model_output_cost,
            model_estimated_cost,
        )
    if export_repo_csv is not None:
        _write_repo_csv(
            export_repo_csv,
            repo_events,
            repo_input_tokens,
            repo_cached_tokens,
            repo_output_tokens,
            repo_non_cached_cost,
            repo_cached_cost,
            repo_output_cost,
            repo_total_cost,
        )

    report_lines: list[str] = []
    report_lines.append(f"Sessions directory: {sessions_dir}")
    report_lines.append("")
    report_lines.append("Data quality")
    report_lines.append(f"Files scanned: {files_scanned}")
    report_lines.append(f"Valid token events: {summary.events}")
    report_lines.append(f"Duplicate events skipped: {duplicate_events_skipped}")
    report_lines.append(f"Lines scanned: {lines_scanned}")
    report_lines.append(f"Malformed JSON lines: {malformed_json_lines}")
    report_lines.append(f"Missing payload/type: {missing_payload_type}")
    report_lines.append(f"Missing token fields: {missing_token_fields}")
    report_lines.append("")
    report_lines.append("Token totals")
    report_lines.append(f"Input tokens:            {_human_tokens(summary.input_tokens)}")
    report_lines.append(f"Cached input tokens:     {_human_tokens(summary.cached_input_tokens)}")
    report_lines.append(f"Non-cached input:        {_human_tokens(non_cached_input)}")
    report_lines.append(f"Output tokens:           {_human_tokens(summary.output_tokens)}")
    report_lines.append(f"Reasoning tokens:        {_human_tokens(summary.reasoning_output_tokens)}")
    report_lines.append(f"Cache ratio: {_fmt_pct(summary.cached_input_tokens, summary.input_tokens)}")
    report_lines.append(f"Effective new tokens estimate: {_fmt_tokens(effective_new_tokens)}")
    report_lines.append(
        "Usage tokens estimate (sum last_token_usage): "
        f"{_fmt_tokens(summary.total_tokens)}"
    )
    report_lines.append(
        "Session final cumulative total "
        f"(sum per-session total_token_usage): {_fmt_tokens(session_final_cumulative_total)}"
    )
    report_lines.append("")
    report_lines.append("API-equivalent estimate (model-based)")
    report_lines.append("(using configured per-model pricing)")
    report_lines.append("")
    report_lines.append(
        f"Non-cached input:   {_fmt_usd(sum(model_non_cached_input_cost.values()))}"
    )
    report_lines.append(f"Cached input:       {_fmt_usd(sum(model_cached_input_cost.values()))}")
    report_lines.append(f"Output:             {_fmt_usd(sum(model_output_cost.values()))}")
    report_lines.append("")
    report_lines.append(f"Estimated total:    {_fmt_usd(estimated_total_cost)}")
    report_lines.append("")
    report_lines.append("Estimated cost by model")
    for model, cost in sorted(model_estimated_cost.items(), key=lambda item: item[1], reverse=True):
        report_lines.append(f"{model}: {_fmt_usd(cost)}")
    report_lines.append("")
    report_lines.append("NOTE:")
    report_lines.append("This is NOT the real OpenAI infrastructure cost.")
    report_lines.append("This is only a rough estimate using configured public API pricing.")
    report_lines.append("")
    report_lines.append("Event distribution")
    report_lines.append(f"Average tokens/event: {avg_tokens_per_event:,.1f}")
    report_lines.append(f"Median tokens/event: {median_tokens_per_event:,.1f}")
    report_lines.append("")
    report_lines.append("Top 10 heaviest events")
    for event in top_heaviest_events:
        report_lines.append(
            f"{event.timestamp.isoformat()} | {event.model or 'unknown'} | "
            f"total={event.total_tokens:,} input={event.input_tokens:,} "
            f"cached={event.cached_input_tokens:,} output={event.output_tokens:,} "
            f"reasoning={event.reasoning_output_tokens:,}"
        )
    report_lines.append("")
    report_lines.append("Breakdown by day (usage estimate)")
    for day in sorted(daily_total_tokens):
        report_lines.append(f"{day}: {_fmt_tokens(daily_total_tokens[day])}")
    report_lines.append("")
    report_lines.append("Breakdown by model (usage estimate)")
    for model, total in sorted(model_total_tokens.items(), key=lambda item: item[1], reverse=True):
        report_lines.append(f"{model}: {_fmt_tokens(total)}")
    report_lines.append("")
    report_lines.append("Breakdown by reasoning effort (usage estimate)")
    for effort, total in sorted(effort_total_tokens.items(), key=lambda item: item[1], reverse=True):
        report_lines.append(f"{effort}: {_fmt_tokens(total)}")
    report_lines.append("")
    report_lines.append("Breakdown by model + reasoning effort (usage estimate)")
    for key, total in sorted(model_effort_total_tokens.items(), key=lambda item: item[1], reverse=True):
        report_lines.append(f"{key}: {_fmt_tokens(total)}")
    report_lines.append("")
    report_lines.append("Breakdown by repository")
    for repo, events_count in sorted(repo_events.items(), key=lambda item: repo_total_cost[item[0]], reverse=True):
        report_lines.append(
            f"{repo}: events={events_count:,} tokens={_fmt_tokens(repo_input_tokens[repo] + repo_output_tokens[repo])} "
            f"cost={_fmt_usd(repo_total_cost[repo])}"
        )
    report_lines.append("")
    report_lines.append("Cache efficiency by day")
    for day in sorted(daily_input_tokens):
        report_lines.append(
            f"{day}: {_fmt_pct(daily_cached_tokens[day], daily_input_tokens[day])} "
            f"({daily_cached_tokens[day]:,}/{daily_input_tokens[day]:,})"
        )
    report_lines.append("")
    if export_events_csv is not None:
        report_lines.append(f"Events CSV: {export_events_csv}")
    if export_daily_csv is not None:
        report_lines.append(f"Daily CSV: {export_daily_csv}")
    if export_model_costs_csv is not None:
        report_lines.append(f"Model costs CSV: {export_model_costs_csv}")
    if export_repo_csv is not None:
        report_lines.append(f"Repo CSV: {export_repo_csv}")

    report_text = "\n".join(report_lines).rstrip() + "\n"
    print(report_text, end="")

    if save_report is not None:
        save_report.parent.mkdir(parents=True, exist_ok=True)
        save_report.write_text(report_text, encoding="utf-8")
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    config = load_app_config(args.config)

    if args.command == "summary":
        return cmd_summary(
            args.sessions_dir or config.sessions_dir,
            args.include_archived_sessions or config.include_archived_sessions,
            args.export_events_csv,
            args.export_daily_csv,
            args.save_report,
            args.export_model_costs_csv,
            args.export_repo_csv,
        )
    if args.command == "import-sqlite":
        source_device = args.source_device or config.source_device
        source_account = args.source_account or config.source_account
        result = import_token_events_to_sqlite(
            db_path=args.db_path or config.sqlite_db_path,
            sessions_dir=args.sessions_dir or config.sessions_dir,
            include_archived_sessions=(
                args.include_archived_sessions or config.include_archived_sessions
            ),
            source_device=source_device,
            source_account=source_account,
            pricing=MODEL_PRICING_USD_PER_MILLION,
            default_pricing=DEFAULT_PRICING_USD_PER_MILLION,
        )
        print(f"DB: {args.db_path or config.sqlite_db_path}")
        print(f"Files scanned: {result['files_scanned']}")
        print(f"Lines scanned: {result['lines_scanned']}")
        print(f"Malformed JSON lines: {result['malformed_json_lines']}")
        print(f"Missing payload/type: {result['missing_payload_type']}")
        print(f"Missing token fields: {result['missing_token_fields']}")
        print(f"Non-token events: {result['non_token_events']}")
        print(f"Inserted raw events: {result['raw_inserted']}")
        print(f"Skipped raw duplicates: {result['raw_skipped_duplicate']}")
        print(f"Inserted token events: {result['token_inserted']}")
        print(f"Skipped token duplicates: {result['token_skipped_duplicate']}")
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
