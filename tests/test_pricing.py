from __future__ import annotations

from codex_usage.pricing import cost_breakdown_usd


def test_cost_breakdown_marks_unknown_model_default_pricing() -> None:
    cost = cost_breakdown_usd(
        model="future-model",
        input_tokens=100,
        cached_input_tokens=20,
        output_tokens=10,
    )

    assert cost.used_default_pricing is True


def test_cost_breakdown_marks_known_model_configured_pricing() -> None:
    cost = cost_breakdown_usd(
        model="gpt-5.4",
        input_tokens=100,
        cached_input_tokens=20,
        output_tokens=10,
    )

    assert cost.used_default_pricing is False
