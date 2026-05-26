from __future__ import annotations

import argparse
import csv
from pathlib import Path

from codex_usage.config import load_app_config
from codex_usage.db import import_token_events_to_sqlite
from codex_usage.pricing import (
    DEFAULT_PRICING_USD_PER_MILLION,
    MODEL_PRICING_USD_PER_MILLION,
    cost_breakdown_usd,
)
from codex_usage.text_report import render_summary_report
from codex_usage.usage_summary import build_usage_summary_data


def _cost_components_usd(
    model: str | None,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
) -> tuple[float, float, float]:
    cost = cost_breakdown_usd(
        model=model,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
    )
    return (cost.non_cached_input_usd, cost.cached_input_usd, cost.output_usd)


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
    data = build_usage_summary_data(
        sessions_dir,
        include_archived_sessions=include_archived_sessions,
    )
    if export_events_csv is not None:
        _write_events_csv(export_events_csv, data.events)
    if export_daily_csv is not None:
        _write_daily_csv(
            export_daily_csv,
            data.daily_events,
            data.daily_input_tokens,
            data.daily_cached_tokens,
            data.daily_output_tokens,
            data.daily_non_cached_input_cost,
            data.daily_cached_input_cost,
            data.daily_output_cost,
            data.daily_estimated_cost,
        )
    if export_model_costs_csv is not None:
        _write_model_costs_csv(
            export_model_costs_csv,
            data.model_non_cached_input_cost,
            data.model_cached_input_cost,
            data.model_output_cost,
            data.model_estimated_cost,
        )
    if export_repo_csv is not None:
        _write_repo_csv(
            export_repo_csv,
            data.repo_events,
            data.repo_input_tokens,
            data.repo_cached_tokens,
            data.repo_output_tokens,
            data.repo_non_cached_cost,
            data.repo_cached_cost,
            data.repo_output_cost,
            data.repo_total_cost,
        )

    report_lines = [render_summary_report(sessions_dir, data).rstrip(), ""]
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
        print(f"Token events using default pricing: {result['default_pricing_token_events']}")
        print(f"Inserted raw events: {result['raw_inserted']}")
        print(f"Skipped raw duplicates: {result['raw_skipped_duplicate']}")
        print(f"Inserted token events: {result['token_inserted']}")
        print(f"Skipped token duplicates: {result['token_skipped_duplicate']}")
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
