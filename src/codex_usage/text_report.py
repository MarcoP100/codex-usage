from __future__ import annotations

from pathlib import Path

from codex_usage.usage_summary import UsageSummaryData


def human_tokens(value: int) -> str:
    abs_value = abs(value)
    if abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs_value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def fmt_tokens(value: int) -> str:
    return f"{value:,} ({human_tokens(value)})"


def fmt_pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "n/a"
    return f"{(numerator / denominator) * 100:.1f}%"


def fmt_usd(value: float) -> str:
    return f"${value:,.1f}"


def render_summary_report(sessions_dir: Path, data: UsageSummaryData) -> str:
    summary = data.summary
    report_lines: list[str] = []
    report_lines.append(f"Sessions directory: {sessions_dir}")
    report_lines.append("")
    report_lines.append("Data quality")
    report_lines.append(f"Files scanned: {data.data_quality.files_scanned}")
    report_lines.append(f"Valid token events: {summary.events}")
    report_lines.append(f"Duplicate events skipped: {data.duplicate_events_skipped}")
    report_lines.append(f"Lines scanned: {data.data_quality.lines_scanned}")
    report_lines.append(f"Malformed JSON lines: {data.data_quality.malformed_json_lines}")
    report_lines.append(f"Missing payload/type: {data.data_quality.missing_payload_type}")
    report_lines.append(f"Missing token fields: {data.data_quality.missing_token_fields}")
    report_lines.append("")
    report_lines.append("Token totals")
    report_lines.append(f"Input tokens:            {human_tokens(summary.input_tokens)}")
    report_lines.append(f"Cached input tokens:     {human_tokens(summary.cached_input_tokens)}")
    report_lines.append(f"Non-cached input:        {human_tokens(data.non_cached_input)}")
    report_lines.append(f"Output tokens:           {human_tokens(summary.output_tokens)}")
    report_lines.append(f"Reasoning tokens:        {human_tokens(summary.reasoning_output_tokens)}")
    report_lines.append(f"Cache ratio: {fmt_pct(summary.cached_input_tokens, summary.input_tokens)}")
    report_lines.append(f"Effective new tokens estimate: {fmt_tokens(data.effective_new_tokens)}")
    report_lines.append(
        "Usage tokens estimate (sum last_token_usage): "
        f"{fmt_tokens(summary.total_tokens)}"
    )
    report_lines.append(
        "Session final cumulative total "
        f"(sum per-session total_token_usage): {fmt_tokens(data.session_final_cumulative_total)}"
    )
    report_lines.append("")
    report_lines.append("API-equivalent estimate (model-based)")
    report_lines.append("(using configured per-model pricing)")
    report_lines.append("")
    report_lines.append(
        f"Non-cached input:   {fmt_usd(sum(data.model_non_cached_input_cost.values()))}"
    )
    report_lines.append(f"Cached input:       {fmt_usd(sum(data.model_cached_input_cost.values()))}")
    report_lines.append(f"Output:             {fmt_usd(sum(data.model_output_cost.values()))}")
    report_lines.append("")
    report_lines.append(f"Estimated total:    {fmt_usd(data.estimated_total_cost)}")
    report_lines.append("")
    report_lines.append("Estimated cost by model")
    for model, cost in sorted(data.model_estimated_cost.items(), key=lambda item: item[1], reverse=True):
        report_lines.append(f"{model}: {fmt_usd(cost)}")
    report_lines.append("")
    report_lines.append("NOTE:")
    report_lines.append("This is NOT the real OpenAI infrastructure cost.")
    report_lines.append("This is only a rough estimate using configured public API pricing.")
    report_lines.append("")
    report_lines.append("Event distribution")
    report_lines.append(f"Average tokens/event: {data.average_tokens_per_event:,.1f}")
    report_lines.append(f"Median tokens/event: {data.median_tokens_per_event:,.1f}")
    report_lines.append("")
    report_lines.append("Top 10 heaviest events")
    for event in data.top_heaviest_events:
        report_lines.append(
            f"{event.timestamp.isoformat()} | {event.model or 'unknown'} | "
            f"total={event.total_tokens:,} input={event.input_tokens:,} "
            f"cached={event.cached_input_tokens:,} output={event.output_tokens:,} "
            f"reasoning={event.reasoning_output_tokens:,}"
        )
    report_lines.append("")
    report_lines.append("Breakdown by day (usage estimate)")
    for day in sorted(data.daily_total_tokens):
        report_lines.append(f"{day}: {fmt_tokens(data.daily_total_tokens[day])}")
    report_lines.append("")
    report_lines.append("Breakdown by model (usage estimate)")
    for model, total in sorted(data.model_total_tokens.items(), key=lambda item: item[1], reverse=True):
        report_lines.append(f"{model}: {fmt_tokens(total)}")
    report_lines.append("")
    report_lines.append("Breakdown by reasoning effort (usage estimate)")
    for effort, total in sorted(data.effort_total_tokens.items(), key=lambda item: item[1], reverse=True):
        report_lines.append(f"{effort}: {fmt_tokens(total)}")
    report_lines.append("")
    report_lines.append("Breakdown by model + reasoning effort (usage estimate)")
    for key, total in sorted(data.model_effort_total_tokens.items(), key=lambda item: item[1], reverse=True):
        report_lines.append(f"{key}: {fmt_tokens(total)}")
    report_lines.append("")
    report_lines.append("Breakdown by repository")
    for repo, events_count in sorted(data.repo_events.items(), key=lambda item: data.repo_total_cost[item[0]], reverse=True):
        report_lines.append(
            f"{repo}: events={events_count:,} tokens={fmt_tokens(data.repo_input_tokens[repo] + data.repo_output_tokens[repo])} "
            f"cost={fmt_usd(data.repo_total_cost[repo])}"
        )
    report_lines.append("")
    report_lines.append("Cache efficiency by day")
    for day in sorted(data.daily_input_tokens):
        report_lines.append(
            f"{day}: {fmt_pct(data.daily_cached_tokens[day], data.daily_input_tokens[day])} "
            f"({data.daily_cached_tokens[day]:,}/{data.daily_input_tokens[day]:,})"
        )
    return "\n".join(report_lines).rstrip() + "\n"
