"""
Execution: Trade execution and position sync.
Places orders (paper or live CLOB), logs to state.
"""
import httpx
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from state.database import Database

CLOB_API_URL = "https://clob.polymarket.com"


class TradeExecutor:
    def __init__(self, db: Any, api_key: str | None = None, api_secret: str | None = None):
        from config import POLYMARKET_API_KEY, POLYMARKET_SECRET
        self.db = db
        self.api_key = api_key or POLYMARKET_API_KEY or ""
        self.api_secret = api_secret or POLYMARKET_SECRET or ""
        self._has_clob = bool(self.api_key and self.api_secret)

    def place_order(
        self,
        market_id: str,
        outcome: str,
        side: str,
        size: float,
        price: float,
        token_id: str | None = None,
    ) -> dict[str, Any]:
        """Place order; if CLOB not configured, paper-trade (log only)."""
        if self._has_clob and token_id:
            result = self._clob_order(token_id, side, size, price)
            order_id = result.get("orderID") or result.get("id", "")
            self.db.log_trade(market_id, outcome, side, size, price, order_id)
            return result
        self.db.log_trade(market_id, outcome, side, size, price, None)
        return {"status": "logged", "paper": True}

    def _clob_order(self, token_id: str, side: str, size: float, price: float) -> dict[str, Any]:
        """Stub: real impl needs CLOB signing (py-clob-client)."""
        with httpx.Client(timeout=15.0) as client:
            r = client.post(
                f"{CLOB_API_URL}/order",
                json={"token_id": token_id, "side": side, "size": size, "price": price},
            )
            r.raise_for_status()
            return r.json() if r.content else {}

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        if not self._has_clob:
            return {"status": "no_clob", "order_id": order_id}
        with httpx.Client(timeout=15.0) as client:
            r = client.delete(f"{CLOB_API_URL}/order/{order_id}")
            r.raise_for_status()
            return r.json() if r.content else {}

    def sync_positions(self) -> list[dict[str, Any]]:
        """Sync from CLOB into state DB if configured; return current positions."""
        if self._has_clob:
            positions = self._clob_positions()
            for pos in positions:
                self.db.upsert_position(
                    pos.get("market_id", ""),
                    pos.get("outcome", ""),
                    pos.get("size", 0.0),
                    pos.get("avg_price", 0.0),
                )
        return self.db.get_positions()

    def _clob_positions(self) -> list[dict[str, Any]]:
        """Stub: fetch positions from CLOB."""
        with httpx.Client(timeout=15.0) as client:
            r = client.get(f"{CLOB_API_URL}/positions")
            if r.status_code != 200:
                return []
            data = r.json()
            return data.get("positions", data) if isinstance(data, dict) else []
