"""
Analysis Layer: Edge detector (Kelly sizing).
Given LLM output (confidence, direction) and market price, compute suggested fraction to bet.
"""
from typing import Any


def kelly_fraction(
    p: float,
    b: float = 1.0,
    q: float | None = None,
) -> float:
    """
    Kelly criterion: f* = (p*b - q) / b = p - q/b.
    p = perceived probability of winning, q = 1-p, b = odds (payoff per unit staked).
    For binary outcome at price 'price': b = (1 - price) / price (for Yes), so
    f* = p - (1-p)*price/(1-price) normalized to [0, 1] cap.
    """
    if q is None:
        q = 1.0 - p
    if b <= 0:
        return 0.0
    f = (p * b - q) / b
    return max(0.0, min(1.0, f))


def kelly_for_binary(
    perceived_prob: float,
    market_price: float,
    cap_fraction: float = 0.25,
) -> float:
    """
    For a binary outcome: market_price is current Yes price (0..1).
    perceived_prob is our estimated probability for Yes.
    Odds: if we buy Yes at price, we get 1 per share if Yes, so b = (1 - price) / price.
    Kelly: f = p - (1-p)/(b) = p - (1-p)*price/(1-price).
    Then cap at cap_fraction (e.g. 0.25 = quarter Kelly).
    """
    if market_price <= 0 or market_price >= 1:
        return 0.0
    b = (1.0 - market_price) / market_price
    q = 1.0 - perceived_prob
    f = (perceived_prob * b - q) / b
    f = max(0.0, min(1.0, f))
    return min(f, cap_fraction)


class EdgeDetector:
    def __init__(self, kelly_cap: float = 0.25):
        self.kelly_cap = kelly_cap

    def size(
        self,
        llm_output: dict[str, Any],
        market_price_yes: float,
    ) -> dict[str, Any]:
        """
        Given LLM reasoning output and current Yes price, return suggested size and edge.
        """
        confidence = float(llm_output.get("confidence_0_1", 0.0))
        direction = (llm_output.get("direction") or "No").strip().lower()
        # If we favor No, perceived prob for Yes is low
        if direction == "no":
            perceived_prob_yes = 1.0 - confidence
        else:
            perceived_prob_yes = confidence

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
