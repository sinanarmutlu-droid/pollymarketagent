"""
State Layer: SQLite DB for positions and trade log.
"""
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Any


class StateDB:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path or "state.db")
        self._conn: sqlite3.Connection | None = None
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_schema(self) -> None:
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT NOT NULL,
                outcome TEXT NOT NULL,
                size REAL NOT NULL,
                avg_price REAL NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(market_id, outcome)
            );
            CREATE TABLE IF NOT EXISTS trade_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_id TEXT NOT NULL,
                outcome TEXT NOT NULL,
                side TEXT NOT NULL,
                size REAL NOT NULL,
                price REAL NOT NULL,
                order_id TEXT,
                created_at TEXT NOT NULL
            );
        """)
        conn.commit()

    def upsert_position(
        self,
        market_id: str,
        outcome: str,
        size: float,
        avg_price: float,
    ) -> None:
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        conn.execute(
            """
            INSERT INTO positions (market_id, outcome, size, avg_price, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(market_id, outcome) DO UPDATE SET
                size = excluded.size,
                avg_price = excluded.avg_price,
                updated_at = excluded.updated_at
            """,
            (market_id, outcome, size, avg_price, now),
        )
        conn.commit()

    def get_positions(self) -> list[dict[str, Any]]:
        conn = self._get_conn()
        cur = conn.execute("SELECT * FROM positions")
        return [dict(row) for row in cur.fetchall()]

    def log_trade(
        self,
        market_id: str,
        outcome: str,
        side: str,
        size: float,
        price: float,
        order_id: str | None = None,
    ) -> None:
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        conn.execute(
            """
            INSERT INTO trade_log (market_id, outcome, side, size, price, order_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (market_id, outcome, side, size, price, order_id or "", now),
        )
        conn.commit()

    def get_trade_log(self, limit: int = 100) -> list[dict[str, Any]]:
        conn = self._get_conn()
        cur = conn.execute(
            "SELECT * FROM trade_log ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
