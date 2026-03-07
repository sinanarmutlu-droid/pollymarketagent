"""
Data: Markets, orderbook, and prices (Polymarket Gamma + CLOB).
"""
import logging
import httpx
from typing import Any

logger = logging.getLogger(__name__)

GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"
CLOB_ORDERBOOK_URL = "https://clob.polymarket.com/book"


class MarketFetcher:
    def __init__(
        self,
        gamma_url: str = GAMMA_MARKETS_URL,
        clob_url: str = CLOB_ORDERBOOK_URL,
    ):
        self.gamma_url = gamma_url.rstrip("/")
        self.clob_url = clob_url.rstrip("/")

    def get_markets(
        self,
        limit: int = 100,
        closed: bool = False,
        **params: Any,
    ) -> list[dict[str, Any]]:
        """Fetch markets from Gamma API."""
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                self.gamma_url,
                params={"limit": limit, "closed": str(closed).lower(), **params},
            )
            r.raise_for_status()
            return r.json()

    def get_market(self, condition_id: str) -> dict[str, Any] | None:
        """Fetch a single market by condition_id."""
        with httpx.Client(timeout=30.0) as client:
            r = client.get(f"{self.gamma_url}/{condition_id}")
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()

    def get_orderbook(self, token_id: str) -> dict[str, Any]:
        """Fetch orderbook for one token. API requires a single token_id per request."""
        if isinstance(token_id, list):
            token_id = token_id[0] if token_id else ""
        token_id = str(token_id).strip()
        with httpx.Client(timeout=15.0) as client:
            r = client.get(self.clob_url, params={"token_id": token_id})
            r.raise_for_status()
            return r.json()

    def get_orderbooks(self, token_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Fetch orderbooks for multiple tokens (one GET per token_id)."""
        result = {}
        for tid in token_ids:
            single = tid[0] if isinstance(tid, list) else tid
            single = str(single).strip()
            if not single:
                continue
            try:
                result[single] = self.get_orderbook(single)
            except Exception:
                result[single] = {}
        return result

    def mid_price(self, token_id: str) -> float | None:
        """Get best price: use last_trade_price if spread is wide, else mid-price."""
        try:
            book = self.get_orderbook(token_id)
            bids = book.get("bids") or []
            asks = book.get("asks") or []
            last_trade = book.get("last_trade_price")
            
            # Prefer last_trade_price (avoids 0.5 when spread is 0.01–0.99)
            if last_trade:
                try:
                    ltp = float(last_trade)
                    if 0 < ltp < 1:
                        return ltp
                except (ValueError, TypeError):
                    pass

            if not bids and not asks:
                return None

            best_bid = float(bids[0]["price"]) if bids else 0.0
            best_ask = float(asks[0]["price"]) if asks else 1.0
            spread = best_ask - best_bid

            if spread > 0.20:
                if bids and asks:
                    bid_size = float(bids[0].get("size", 0) or 0)
                    ask_size = float(asks[0].get("size", 0) or 0)
                    total = bid_size + ask_size
                    if total > 0:
                        return (best_bid * bid_size + best_ask * ask_size) / total

            return (best_bid + best_ask) / 2.0
        except Exception as e:
            logger.warning("mid_price failed for %s: %s", token_id[:20], e)
            return None

    def get_prices(self, token_ids: list[str]) -> dict[str, float | None]:
        """Mid price per token."""
        return {tid: self.mid_price(tid) for tid in token_ids}
