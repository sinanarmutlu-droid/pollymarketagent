"""
Main entry point: run agent loop every N minutes.
  data → analysis (news → LLM → edge) → execution (risk → trade) → state
"""
import time

from config import ORCHESTRATOR_INTERVAL_MINUTES
from state.database import Database
from data.market_fetcher import MarketFetcher
from data.news_fetcher import NewsFetcher
from analysis.llm_reasoner import LLMReasoner
from analysis.edge_detector import EdgeDetector
from execution.trade_executor import TradeExecutor
from execution.risk_manager import RiskManager


def _token_ids(market: dict) -> list[str]:
    """Extract CLOB token IDs from a Gamma market payload."""
    ids = []
    outcomes = market.get("outcomes") or market.get("outcomePrices") or []
    for o in outcomes if isinstance(outcomes, list) else []:
        if isinstance(o, dict) and o.get("tokenId"):
            ids.append(o["tokenId"])
        elif isinstance(o, str):
            ids.append(o)
    if not ids and market.get("clobTokenIds"):
        ids = market["clobTokenIds"] if isinstance(market["clobTokenIds"], list) else [market["clobTokenIds"]]
    if not ids and market.get("clobTokenId"):
        ids = [market["clobTokenId"]]
    return [t for t in ids if t]


def run_one_cycle(
    db: Database,
    markets: MarketFetcher,
    news: NewsFetcher,
    llm: LLMReasoner,
    edge: EdgeDetector,
    executor: TradeExecutor,
    risk: RiskManager,
    max_markets: int = 5,
) -> None:
    """Single cycle: fetch data → analyze → risk-check → execute."""
    market_list = markets.get_markets(limit=max_markets, closed=False)
    if not market_list:
        return

    m = market_list[0]
    condition_id = m.get("conditionId") or m.get("condition_id") or ""
    question = m.get("question", "")
    token_ids = _token_ids(m)

    price_map = markets.get_prices(token_ids) if token_ids else {}
    market_price_yes = next((p for p in price_map.values() if p is not None), 0.5) or 0.5

    news_results = news.fetch_for_markets([question])
    news_context = str(news_results.get(question, [])[:5])
    current_prices = {k: v for k, v in price_map.items() if v is not None}

    llm_out = llm.reason(
        market_context=question,
        news_context=news_context,
        current_prices=current_prices,
    )
    edge_out = edge.size(llm_out, market_price_yes)

    executor.sync_positions()

    action = edge_out.get("suggested_action")
    kelly = edge_out.get("kelly_fraction", 0) or 0
    if action not in ("buy_yes", "buy_no") or kelly <= 0.01:
        return

    outcome = "Yes" if action == "buy_yes" else "No"
    price = market_price_yes if outcome == "Yes" else (1.0 - market_price_yes)
    size = 10.0 * kelly
    size = risk.capped_size(size, price)

    allowed, reason = risk.approve_trade(condition_id, outcome, size, price)
    if not allowed:
        return

    executor.place_order(
        market_id=condition_id,
        outcome=outcome,
        side="BUY",
        size=size,
        price=price,
        token_id=token_ids[0] if token_ids else None,
    )


def main() -> None:
    db = Database()
    markets = MarketFetcher()
    news = NewsFetcher()
    llm = LLMReasoner()
    edge = EdgeDetector()
    executor = TradeExecutor(db)
    risk = RiskManager(db)

    print(f"Polymarket agent started (interval={ORCHESTRATOR_INTERVAL_MINUTES} min). Ctrl+C to stop.")
    while True:
        try:
            run_one_cycle(db, markets, news, llm, edge, executor, risk)
        except Exception as e:
            print(f"Cycle error: {e}")
        time.sleep(ORCHESTRATOR_INTERVAL_MINUTES * 60.0)


if __name__ == "__main__":
    main()
