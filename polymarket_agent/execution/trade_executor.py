"""
Execution: Trade execution and position sync.
"""
import logging
import os
from typing import Any, TYPE_CHECKING
import httpx

if TYPE_CHECKING:
    from state.database import Database

logger = logging.getLogger(__name__)
CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137


def _get_clob_client():
    from config import POLYMARKET_PRIVATE_KEY
    key = (POLYMARKET_PRIVATE_KEY or "").strip()
    if not key:
        return None
    try:
        from py_clob_client.client import ClobClient
    except ImportError as e:
        logger.warning("py-clob-client not installed: %s", e)
        return None
    proxy_url = os.environ.get("PROXY_URL", "").strip()
    if proxy_url:
        try:
            import py_clob_client.http_helpers.helpers as _h
            t = httpx.HTTPTransport(proxy=httpx.Proxy(url=proxy_url))
            _h._http_client = httpx.Client(transport=t, http2=True)
        except Exception as e:
            logger.warning("Proxy setup failed: %s", e)
    try:
        client = ClobClient(CLOB_HOST, key=key, chain_id=CHAIN_ID, signature_type=0)
        client.set_api_creds(client.create_or_derive_api_creds())
        return client
    except Exception as e:
        logger.exception("Failed to create ClobClient: %s", e)
        return None


class TradeExecutor:
    def __init__(self, db: Any, api_key: str | None = None, api_secret: str | None = None):
        from config import POLYMARKET_API_KEY, POLYMARKET_SECRET, PAPER_TRADING
        self.db = db
        self.api_key = api_key or POLYMARKET_API_KEY or ""
        self.api_secret = api_secret or POLYMARKET_SECRET or ""
        self._client = _get_clob_client()
        self._has_clob = self._client is not None
        self._paper_trading = PAPER_TRADING

    def get_balance(self) -> float:
        """Fetch wallet USDC balance from Polygon via Web3 (not CLOB API)."""
        from config import POLYMARKET_PRIVATE_KEY, POLYGON_RPC_URL
        key = (POLYMARKET_PRIVATE_KEY or "").strip()
        if not key:
            return 0.0
        try:
            from web3 import Web3
            from eth_account import Account
            w3 = Web3(Web3.HTTPProvider(POLYGON_RPC_URL or "https://polygon-rpc.com"))
            account = Account.from_key(key)
            address = account.address
            USDC = Web3.to_checksum_address("0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359")
            abi = [
                {"name": "balanceOf", "type": "function", "inputs": [{"name": "account", "type": "address"}], "outputs": [{"name": "", "type": "uint256"}], "stateMutability": "view"}
            ]
            contract = w3.eth.contract(address=USDC, abi=abi)
            balance = contract.functions.balanceOf(address).call()
            return float(balance) / 1e6
        except Exception as e:
            logger.warning("Failed to fetch balance: %s", e)
            return 0.0

    def place_order(self, market_id, outcome, side, size, price, token_id=None):
        if self._paper_trading:
            logger.info("PAPER_TRADING enabled - skipping real order")
            self.db.log_trade(market_id, outcome, side, size, price, None)
            return {"status": "paper", "paper": True}

        if self._has_clob and token_id:
            trade_cost = size * price
            balance = self.get_balance()
            if balance < trade_cost:
                logger.warning("Insufficient balance: %.2f USDC < %.2f required", balance, trade_cost)
                return {"status": "insufficient_balance", "balance": balance, "required": trade_cost, "paper": False}

            try:
                from py_clob_client.clob_types import OrderArgs, OrderType
                from py_clob_client.order_builder.constants import BUY
                order_args = OrderArgs(token_id=token_id, price=round(price, 4), size=round(size, 4), side=BUY)
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

    def cancel_order(self, order_id):
        if not self._has_clob:
            return {"status": "no_clob", "order_id": order_id}
        try:
            self._client.cancel(order_id)
            return {"status": "cancelled", "order_id": order_id}
        except Exception as e:
            logger.exception("Cancel order failed: %s", e)
            return {"status": "error", "order_id": order_id, "error": str(e)}

    def sync_positions(self):
        if self._has_clob:
            try:
                positions = self._clob_positions()
                for pos in positions:
                    self.db.upsert_position(pos.get("market_id", ""), pos.get("outcome", ""), pos.get("size", 0.0), pos.get("avg_price", 0.0))
            except Exception as e:
                logger.exception("Sync positions failed: %s", e)
        return self.db.get_positions()

    def _clob_positions(self):
        try:
            trades = self._client.get_trades()
        except Exception:
            return []
        seen = {}
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
