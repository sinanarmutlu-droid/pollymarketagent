"""
Execution: Risk limits (position size, daily loss).
"""
from datetime import date
from typing import Any


class RiskManager:
    def __init__(
        self,
        db: Any,
        max_position_size: float | None = None,
        max_daily_loss: float | None = None,
    ):
        from config import MAX_POSITION_SIZE, MAX_DAILY_LOSS
        self.db = db
        self.max_position_size = max_position_size if max_position_size is not None else MAX_POSITION_SIZE
        self.max_daily_loss = max_daily_loss if max_daily_loss is not None else MAX_DAILY_LOSS

    def approve_trade(
        self,
        market_id: str,
        outcome: str,
        size: float,
        price: float,
    ) -> tuple[bool, str]:
        """
        Return (allowed, reason).
        Checks: single-trade size vs max_position_size, daily PnL vs max_daily_loss.
        """
        if size <= 0:
            return False, "size must be positive"
        notional = size * price
        if notional > self.max_position_size:
            return False, f"notional {notional:.2f} exceeds max position size {self.max_position_size}"
        daily_pnl = self._daily_pnl()
        if daily_pnl is not None and daily_pnl <= -self.max_daily_loss:
            return False, f"daily loss limit reached ({daily_pnl:.2f})"
        return True, ""

    def _daily_pnl(self) -> float | None:
        """Approximate daily PnL from trade log (simplified: sum (size * (1 - price)) for sells, etc.)."""
        log = self.db.get_trade_log(limit=500)
        today = date.today().isoformat()
        total = 0.0
        for row in log:
            created = row.get("created_at", "")[:10]
            if created != today:
                continue
            side = (row.get("side") or "").upper()
            size = float(row.get("size", 0))
            price = float(row.get("price", 0))
            if side == "BUY":
                total -= size * price
            else:
                total += size * price
        return total if log else None

    def capped_size(self, requested_size: float, price: float) -> float:
        """Return size capped by max position size."""
        if price <= 0:
            return 0.0
        max_size = self.max_position_size / price
        return min(requested_size, max_size)
