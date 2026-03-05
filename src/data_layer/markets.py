"""
Data Layer: Markets client (Polymarket / Gamma API).
"""
import httpx
from typing import Any

# Polymarket Gamma API (public)
GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"


class MarketsClient:
    def __init__(self, base_url: str = GAMMA_MARKETS_URL):
        self.base_url = base_url.rstrip("/")

    def get_markets(
        self,
        limit: int = 100,
        closed: bool = False,
        **params: Any,
    ) -> list[dict[str, Any]]:
        """Fetch markets from Gamma API."""
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                self.base_url,
                params={"limit": limit, "closed": str(closed).lower(), **params},
            )
            r.raise_for_status()
            return r.json()

    def get_market(self, condition_id: str) -> dict[str, Any] | None:
        """Fetch a single market by condition_id."""
        with httpx.Client(timeout=30.0) as client:
            r = client.get(f"{self.base_url}/{condition_id}")
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
