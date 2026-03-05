"""
Analysis Layer: LLM Reasoner (Claude).
"""
import os
import json
from typing import Any

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


class LLMReasoner:
    def __init__(self, api_key: str | None = None, model: str = "claude-3-5-sonnet-20241022"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model
        self._client = anthropic.Anthropic(api_key=self.api_key) if ANTHROPIC_AVAILABLE and self.api_key else None

    def reason(
        self,
        market_context: str,
        news_context: str,
        current_prices: dict[str, float],
    ) -> dict[str, Any]:
        """
        Ask Claude to reason about edge given market info, news, and prices.
        Returns a dict with keys like: thesis, confidence_0_1, direction (Yes/No), reasoning.
        """
        if not self._client:
            return {
                "thesis": "",
                "confidence_0_1": 0.0,
                "direction": "No",
                "reasoning": "LLM not configured (missing ANTHROPIC_API_KEY or anthropic package).",
            }
        prompt = f"""You are a prediction market analyst. Given the following context, produce a short thesis and confidence.

Market context:
{market_context}

Relevant news (Tavily):
{news_context}

Current prices (outcome -> price):
{json.dumps(current_prices, indent=2)}

Respond in JSON only, with exactly these keys:
- "thesis": one sentence edge thesis
- "confidence_0_1": number between 0 and 1
- "direction": "Yes" or "No" (which outcome you favor)
- "reasoning": 2-3 sentence explanation
"""
        try:
            msg = self._client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            text = msg.content[0].text if msg.content else "{}"
            # Extract JSON from response (handle markdown code blocks)
            if "```" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                text = text[start:end]
            return json.loads(text)
        except Exception as e:
            return {
                "thesis": "",
                "confidence_0_1": 0.0,
                "direction": "No",
                "reasoning": str(e),
            }
