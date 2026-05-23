from __future__ import annotations

from aiteamos_schema import ModelProfile


def estimate_profile_call_cost_usd(
    profile: ModelProfile | None,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> float | None:
    if profile is None or profile.spec.pricing is None:
        return None
    pricing = profile.spec.pricing
    cost = float(pricing.requestUsd or 0.0)
    if pricing.inputUsdPer1MTokens is not None:
        cost += max(0, int(input_tokens or 0)) * float(pricing.inputUsdPer1MTokens) / 1_000_000
    if pricing.outputUsdPer1MTokens is not None:
        cost += max(0, int(output_tokens or 0)) * float(pricing.outputUsdPer1MTokens) / 1_000_000
    return round(cost, 8)
