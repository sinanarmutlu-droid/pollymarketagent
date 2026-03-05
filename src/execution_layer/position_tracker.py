"""
Execution Layer: Position tracking.
Sync positions from wallet/CLOB into state layer.
"""
from __future__ import annotations
from typing import Any
from ..state_layer import StateDB
from .wallet_clob import WalletCLOB


class PositionTracker:
    def __init__(self, state_db: StateDB, wallet_clob: WalletCLOB | None = None):
        self.state_db = state_db
        self.wallet_clob = wallet_clob

    def sync_positions(self) -> list[dict[str, Any]]:
        """
        Fetch positions from wallet/CLOB (if configured) and upsert into state DB.
        Returns current positions from state.
        """
        if self.wallet_clob:
            for pos in self.wallet_clob.get_positions():
                self.state_db.upsert_position(
                    market_id=pos.get("market_id", ""),
                    outcome=pos.get("outcome", ""),
                    size=pos.get("size", 0.0),
                    avg_price=pos.get("avg_price", 0.0),
                )
        return self.state_db.get_positions()

    def get_positions(self) -> list[dict[str, Any]]:
        """Read positions from state layer."""
        return self.state_db.get_positions()
