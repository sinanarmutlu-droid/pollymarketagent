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
        if llm_output.get("_error"):
            return {
                "kelly_fraction": 0.0,
                "edge": 0.0,
                "perceived_prob_yes": 0.5,
                "direction": "No",
                "suggested_action": "no_trade",
                "_error": True,
            }

        if "perceived_probability_yes" in llm_output and llm_output["perceived_probability_yes"] is not None:
            perceived_prob_yes = float(llm_output["perceived_probability_yes"])
        else:
            confidence = float(llm_output.get("confidence_0_1", 0.0))
            direction_raw = (llm_output.get("direction") or "No").strip().lower()
            perceived_prob_yes = confidence if direction_raw == "yes" else (1.0 - confidence)

        direction = (llm_output.get("direction") or "No").strip().lower()

        edge = perceived_prob_yes - market_price_yes if direction == "yes" else market_price_yes - perceived_prob_yes

        if edge <= 0:
            return {
                "kelly_fraction": 0.0,
                "edge": edge,
                "perceived_prob_yes": perceived_prob_yes,
                "direction": "Yes" if direction == "yes" else "No",
                "suggested_action": "no_trade",
            }

        if direction == "yes":
            kelly = kelly_for_binary(
                perceived_prob_yes,
                market_price_yes,
                cap_fraction=self.kelly_cap,
            )
        else:
            kelly = kelly_for_binary(
                1.0 - perceived_prob_yes,
                1.0 - market_price_yes,
                cap_fraction=self.kelly_cap,
            )

        return {
            "kelly_fraction": kelly,
            "edge": edge,
            "perceived_prob_yes": perceived_prob_yes,
            "direction": "Yes" if direction == "yes" else "No",
            "suggested_action": "buy_yes" if direction == "yes" else "buy_no",
        }