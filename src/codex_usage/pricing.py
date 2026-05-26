from __future__ import annotations

from dataclasses import dataclass


MODEL_PRICING_USD_PER_MILLION: dict[str, tuple[float, float, float]] = {
    "gpt-5.5": (5.0, 0.5, 30.0),
    "gpt-5.4": (2.5, 0.25, 15.0),
    "gpt-5.4-mini": (0.75, 0.075, 4.5),
    "gpt-5.3-codex": (1.75, 0.175, 14.0),
}
DEFAULT_PRICING_USD_PER_MILLION = MODEL_PRICING_USD_PER_MILLION["gpt-5.5"]


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    non_cached_input_usd: float
    cached_input_usd: float
    output_usd: float
    used_default_pricing: bool

    @property
    def total_usd(self) -> float:
        return self.non_cached_input_usd + self.cached_input_usd + self.output_usd


def usd_from_million_tokens(tokens: int, usd_per_million: float) -> float:
    return (tokens / 1_000_000) * usd_per_million


def cost_breakdown_usd(
    *,
    model: str | None,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    pricing: dict[str, tuple[float, float, float]] = MODEL_PRICING_USD_PER_MILLION,
    default_pricing: tuple[float, float, float] = DEFAULT_PRICING_USD_PER_MILLION,
) -> CostBreakdown:
    model_key = (model or "").strip().lower()
    used_default_pricing = model_key not in pricing
    non_cached_rate, cached_rate, output_rate = pricing.get(model_key, default_pricing)
    non_cached_input = input_tokens - cached_input_tokens
    return CostBreakdown(
        non_cached_input_usd=usd_from_million_tokens(non_cached_input, non_cached_rate),
        cached_input_usd=usd_from_million_tokens(cached_input_tokens, cached_rate),
        output_usd=usd_from_million_tokens(output_tokens, output_rate),
        used_default_pricing=used_default_pricing,
    )
