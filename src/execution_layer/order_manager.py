"""
Execution Layer: Order management.
Place/cancel orders via CLOB; log to state layer.
"""
from __future__ import annotations
from typing import Any
from ..state_layer import StateDB
from .wallet_clob import WalletCLOB


class OrderManager:
    def __init__(self, state_db: StateDB, wallet_clob: WalletCLOB | None = None):
        self.state_db = state_db
        self.wallet_clob = wallet_clob  # Optional: real CLOB client for live orders

    def place_order(
        self,
        market_id: str,
        outcome: str,
        side: str,
        size: float,
        price: float,
        token_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Place order (Yes/No). If wallet_clob not configured, only logs intent.
        """
        if self.wallet_clob and token_id:
            result = self.wallet_clob.place_order(
                token_id=token_id,
                side=side,
                size=size,
                price=price,
            )
            order_id = result.get("orderID") or result.get("id", "")
            self.state_db.log_trade(
                market_id=market_id,
                outcome=outcome,
                side=side,
                size=size,
                price=price,
                order_id=order_id,
            )
            return result
        # Paper/dry run: just log
        self.state_db.log_trade(
            market_id=market_id,
            outcome=outcome,
            side=side,
            size=size,
            price=price,
            order_id=None,
        )
        return {"status": "logged", "paper": True}

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel order by ID if wallet_clob configured."""
        if self.wallet_clob:
            return self.wallet_clob.cancel_order(order_id)
        return {"status": "no_clob", "order_id": order_id}
