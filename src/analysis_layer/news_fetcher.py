"""
Analysis Layer: News fetcher (Tavily).
"""
import os
from typing import Any

try:
    from tavily import TavilyClient
    TAVILY_AVAILABLE = True
except ImportError:
    TAVILY_AVAILABLE = False


class NewsFetcher:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY", "")
        self._client: Any = None
        if TAVILY_AVAILABLE and self.api_key:
            self._client = TavilyClient(api_key=self.api_key)

    def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
    ) -> list[dict[str, Any]]:
        """Fetch news/search results from Tavily."""
        if not TAVILY_AVAILABLE or not self._client:
            return []
        try:
            r = self._client.search(
                query=query,
                max_results=max_results,
                search_depth=search_depth,
            )
            return (r.get("results") or [])
        except Exception:
            return []

    def fetch_for_markets(self, market_queries: list[str]) -> dict[str, list[dict[str, Any]]]:
        """Fetch news for a list of market-related queries."""
        return {q: self.search(q) for q in market_queries}
