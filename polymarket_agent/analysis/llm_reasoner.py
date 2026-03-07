"""
Analysis: LLM Reasoner (Claude).
"""
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


class LLMReasoner:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        from config import ANTHROPIC_API_KEY, LLM_MODEL
        self.api_key = api_key or ANTHROPIC_API_KEY or ""
        self.model = model or LLM_MODEL
        self._client = anthropic.Anthropic(api_key=self.api_key) if ANTHROPIC_AVAILABLE and self.api_key else None
        self._last_call_time = 0.0
        self._min_interval = 2.0  # Rate limit: min 2 seconds between calls

    def reason(
        self,
        market_context: str,
        news_context: str,
        current_prices: dict[str, float],
    ) -> dict[str, Any]:
        """
        Reason about edge given market info, news, and prices.
        Returns: thesis, confidence_0_1, direction (Yes/No), reasoning.
        """
        if not self._client:
            logger.warning("LLM not configured (missing API key or package)")
            return {
                "thesis": "",
                "confidence_0_1": 0.0,
                "direction": "No",
                "reasoning": "LLM not configured (missing ANTHROPIC_API_KEY or anthropic package).",
                "_error": True,
            }

        # Rate limit protection
        elapsed = time.time() - self._last_call_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call_time = time.time()

        prompt = f"""You are a prediction market analyst. Given the following context, produce a short thesis and your perceived probability.

Market context:
{market_context}

Relevant news (Tavily):
{news_context}

Current prices (outcome -> price):
{json.dumps(current_prices, indent=2)}

Respond in JSON only, with exactly these keys:
- "thesis": one sentence edge thesis (required)
- "perceived_probability_yes": your estimated probability that YES wins, between 0.0 and 1.0 (required)
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
            print(f"[LLM RAW] {text}")
            logger.info("LLM raw response: %s", text)
            if "```" in text:
                start = text.find("{")
                end = text.rfind("}") + 1
                text = text[start:end]
            parsed = json.loads(text)

            # Map perceived_probability_yes to confidence_0_1 for edge detector
            if "perceived_probability_yes" in parsed:
                prob = float(parsed["perceived_probability_yes"])
                parsed["confidence_0_1"] = prob if parsed.get("direction", "").lower() == "yes" else (1.0 - prob)
            
            # Validate required fields
            if "thesis" not in parsed or not parsed.get("thesis"):
                print(f"[LLM ERROR] Missing thesis in response: {parsed}")
                logger.warning("LLM response missing thesis: %s", parsed)
                parsed["_error"] = True
            if "perceived_probability_yes" not in parsed or parsed.get("perceived_probability_yes") is None:
                print(f"[LLM ERROR] Missing perceived_probability_yes in response: {parsed}")
                logger.warning("LLM response missing perceived_probability_yes: %s", parsed)
                parsed["_error"] = True
                parsed["reasoning"] = "Missing perceived_probability_yes in LLM response"
            if "direction" not in parsed or parsed.get("direction") not in ("Yes", "No", "yes", "no"):
                print(f"[LLM ERROR] Invalid direction in response: {parsed.get('direction')}")
                logger.warning("LLM response invalid direction: %s", parsed.get("direction"))
                parsed["_error"] = True
                parsed["reasoning"] = "Invalid direction in LLM response"

            print(f"[LLM PARSED] thesis={parsed.get('thesis', '')[:60]}, prob_yes={parsed.get('perceived_probability_yes')}, dir={parsed.get('direction')}")
            logger.info("LLM parsed: thesis=%s, prob_yes=%.2f, dir=%s",
                        parsed.get("thesis", "")[:50], parsed.get("perceived_probability_yes", 0) or 0, parsed.get("direction"))
            return parsed
        except json.JSONDecodeError as e:
            print(f"[LLM ERROR] Invalid JSON: {e}, raw text: {text[:200]}")
            logger.error("LLM response not valid JSON: %s, raw: %s", e, text[:200])
            return {
                "thesis": "",
                "confidence_0_1": 0.0,
                "perceived_probability_yes": 0.0,
                "direction": "No",
                "reasoning": f"Invalid JSON from LLM: {e}",
                "_error": True,
            }
        except Exception as e:
            print(f"[LLM ERROR] Call failed: {e}")
            logger.exception("LLM call failed: %s", e)
            return {
                "thesis": "",
                "confidence_0_1": 0.0,
                "perceived_probability_yes": 0.0,
                "direction": "No",
                "reasoning": str(e),
                "_error": True,
            }
