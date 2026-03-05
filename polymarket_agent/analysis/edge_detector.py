"""
Analysis: Edge detector (Kelly sizing).
"""
from typing import Any


def kelly_for_binary(
    perceived_prob: float,
    market_price: float,
    cap_fraction: float = 0.25,
) -> float:
    """Kelly fraction for binary outcome; cap at cap_fraction."""
    if market_price <= 0 or market_price >= 1:
        return 0.0
    b = (1.0 - market_price) / market_price
    q = 1.0 - perceived_prob
    f = (perceived_prob * b - q) / b
    f = max(0.0, min(1.0, f))
    return min(f, cap_fraction)


class EdgeDetector:
    def __init__(self, kelly_cap: float | None = None):
        from config import KELLY_CAP
        self.kelly_cap = kelly_cap if kelly_cap is not None else KELLY_CAP

    def size(
        self,
        llm_output: dict[str, Any],
        market_price_yes: float,
    ) -> dict[str, Any]:
        """Given LLM output and Yes price, return suggested size and edge."""
        confidence = float(llm_output.get("confidence_0_1", 0.0))
        direction = (llm_output.get("direction") or "No").strip().lower()
        perceived_prob_yes = confidence if direction == "yes" else (1.0 - confidence)

        kelly = kelly_for_binary(
            perceived_prob_yes,
            market_price_yes,
            cap_fraction=self.kelly_cap,
        )
        edge = perceived_prob_yes - market_price_yes if direction == "yes" else market_price_yes - perceived_prob_yes

        return {
            "kelly_fraction": kelly,
            "edge": edge,
            "perceived_prob_yes": perceived_prob_yes,
            "direction": "Yes" if direction == "yes" else "No",
            "suggested_action": "buy_yes" if direction == "yes" and kelly > 0 else ("buy_no" if direction == "no" and kelly > 0 else "no_trade"),
        }
