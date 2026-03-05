"""
Data Layer: Orderbook client (Polymarket CLOB).
"""
import httpx
from typing import Any

CLOB_ORDERBOOK_URL = "https://clob.polymarket.com/book"


class OrderbookClient:
    def __init__(self, base_url: str = CLOB_ORDERBOOK_URL):
        self.base_url = base_url.rstrip("/")

    def get_orderbook(self, token_id: str) -> dict[str, Any]:
        """Fetch orderbook for a single token (outcome)."""
        with httpx.Client(timeout=15.0) as client:
            r = client.get(f"{self.base_url}", params={"token_id": token_id})
            r.raise_for_status()
            return r.json()

    def get_orderbooks(self, token_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Fetch orderbooks for multiple tokens."""
        result = {}
        for tid in token_ids:
            try:
                result[tid] = self.get_orderbook(tid)
            except Exception:
                result[tid] = {}
        return result
