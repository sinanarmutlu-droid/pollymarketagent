"""
Execution: Trade execution and position sync.
Uses py-clob-client for real order placement when POLYMARKET_PRIVATE_KEY is set.
"""
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from state.database import Database

logger = logging.getLogger(__name__)

CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137


def _get_clob_client():
    """Build authenticated ClobClient from POLYMARKET_PRIVATE_KEY; returns None if not configured."""
    from config import POLYMARKET_PRIVATE_KEY
    key = (POLYMARKET_PRIVATE_KEY or "").strip()
    if not key:
        return None
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY
    except ImportError as e:
        logger.warning("py-clob-client not installed: %s", e)
        return None
    try:
        client = ClobClient(
            CLOB_HOST,
            key=key,
            chain_id=CHAIN_ID,
            signature_type=0,  # EOA
        )
        client.set_api_creds(client.create_or_derive_api_creds())
        return client
    except Exception as e:
        logger.exception("Failed to create ClobClient: %s", e)
        return None


class TradeExecutor:
    def __init__(self, db: Any, api_key: str | None = None, api_secret: str | None = None):
        from config import POLYMARKET_API_KEY, POLYMARKET_SECRET
        self.db = db
        self.api_key = api_key or POLYMARKET_API_KEY or ""
        self.api_secret = api_secret or POLYMARKET_SECRET or ""
        self._client = _get_clob_client()
        self._has_clob = self._client is not None

    def place_order(
        self,
        market_id: str,
        outcome: str,
        side: str,
        size: float,
        price: float,
        token_id: str | None = None,
    ) -> dict[str, Any]:
        """Place order via py-clob-client when configured; otherwise paper-trade (log only)."""
        if self._has_clob and token_id:
            try:
                from py_clob_client.clob_types import OrderArgs, OrderType
                from py_clob_client.order_builder.constants import BUY
                order_args = OrderArgs(
                    token_id=token_id,
                    price=round(price, 4),
                    size=round(size, 4),
                    side=BUY,
                )
                signed = self._client.create_order(order_args)
                resp = self._client.post_order(signed, OrderType.GTC)
                order_id = (resp.get("orderID") or resp.get("id") or "").strip()
                self.db.log_trade(market_id, outcome, side, size, price, order_id or None)
                return resp
            except Exception as e:
                logger.exception("Real order placement failed: %s", e)
                self.db.log_trade(market_id, outcome, side, size, price, None)
                return {"status": "error", "error": str(e), "paper": False}
        self.db.log_trade(market_id, outcome, side, size, price, None)
        return {"status": "logged", "paper": True}

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        if not self._has_clob:
            return {"status": "no_clob", "order_id": order_id}
        try:
            self._client.cancel(order_id)
            return {"status": "cancelled", "order_id": order_id}
        except Exception as e:
            logger.exception("Cancel order failed: %s", e)
            return {"status": "error", "order_id": order_id, "error": str(e)}

    def sync_positions(self) -> list[dict[str, Any]]:
        """Sync from CLOB into state DB if configured; return current positions."""
        if self._has_clob:
            try:
                positions = self._clob_positions()
                for pos in positions:
                    self.db.upsert_position(
                        pos.get("market_id", ""),
                        pos.get("outcome", ""),
                        pos.get("size", 0.0),
                        pos.get("avg_price", 0.0),
                    )
            except Exception as e:
                logger.exception("Sync positions failed: %s", e)
        return self.db.get_positions()

    def _clob_positions(self) -> list[dict[str, Any]]:
        """Fetch positions from CLOB via get_trades(); aggregate by market/outcome. Returns [] on error."""
        try:
            trades = self._client.get_trades()
        except Exception:
            return []
        seen: dict[tuple[str, str], dict[str, Any]] = {}
        for t in (trades or []):
            mid = t.get("market") or t.get("market_id", "")
            outcome = t.get("outcome", "")
            key = (mid, outcome)
            size = float(t.get("size", 0) or 0)
            price = float(t.get("price", 0) or 0)
            if key not in seen:
                seen[key] = {"market_id": mid, "outcome": outcome, "size": 0.0, "avg_price": 0.0}
            prev = seen[key]
            old_size = prev["size"]
            prev["size"] += size
            if size > 0 and price > 0:
                prev["avg_price"] = (prev["avg_price"] * old_size + price * size) / prev["size"]
        return list(seen.values())
