"""
Data Layer: Prices (from orderbook mid or Polymarket price API).
"""
from .orderbook import OrderbookClient
from typing import Any


class PricesClient:
    def __init__(self, orderbook_client: OrderbookClient | None = None):
        self.orderbook = orderbook_client or OrderbookClient()

    def mid_price(self, token_id: str) -> float | None:
        """Mid price from orderbook (best bid + best ask) / 2."""
        book = self.orderbook.get_orderbook(token_id)
        bids = book.get("bids") or []
        asks = book.get("asks") or []
        if not bids and not asks:
            return None
        best_bid = float(bids[0]["price"]) if bids else 0.0
        best_ask = float(asks[0]["price"]) if asks else 1.0
        if not bids:
            return best_ask
        if not asks:
            return best_bid
        return (best_bid + best_ask) / 2.0

    def get_prices(self, token_ids: list[str]) -> dict[str, float | None]:
        """Mid price per token."""
        return {tid: self.mid_price(tid) for tid in token_ids}
