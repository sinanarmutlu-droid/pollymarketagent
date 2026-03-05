"""
Agent Orchestrator: runs every N minutes.
  Data Layer → Analysis Layer (News → LLM → Edge) → Execution Layer
  State Layer (SQLite) persists positions and trade log.
"""
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from .state_layer import StateDB
from .data_layer import MarketsClient, OrderbookClient, PricesClient
from .analysis_layer import NewsFetcher, LLMReasoner, EdgeDetector
from .execution_layer import OrderManager, PositionTracker, WalletCLOB

load_dotenv()


def run_one_cycle(
    state_db: StateDB,
    markets: MarketsClient,
    orderbook: OrderbookClient,
    prices: PricesClient,
    news: NewsFetcher,
    llm: LLMReasoner,
    edge: EdgeDetector,
    order_manager: OrderManager,
    position_tracker: PositionTracker,
    max_markets: int = 5,
) -> None:
    """Single orchestration cycle: fetch data → analyze → optionally execute."""
    # 1) Data Layer: get markets and prices
    market_list = markets.get_markets(limit=max_markets, closed=False)
    if not market_list:
        return

    # Build context for first market (example: one market per cycle)
    m = market_list[0]
    condition_id = m.get("conditionId") or m.get("condition_id") or ""
    question = m.get("question", "")
    outcomes = m.get("outcomes") or m.get("outcomePrices") or []
    token_ids = []
    if isinstance(outcomes, list) and outcomes:
        for o in outcomes:
            if isinstance(o, dict) and o.get("tokenId"):
                token_ids.append(o["tokenId"])
            elif isinstance(o, str):
                token_ids.append(o)
    if not token_ids:
        token_ids = [m.get("clobTokenIds", [m.get("clobTokenId")])]
        token_ids = [t for t in (token_ids[0] if isinstance(token_ids[0], list) else token_ids) if t]

    # Prices
    price_map = prices.get_prices(token_ids) if token_ids else {}
    market_price_yes = None
    for tid, p in price_map.items():
        if p is not None:
            market_price_yes = p
            break
    if market_price_yes is None:
        market_price_yes = 0.5

    # 2) Analysis Layer: News → LLM → Edge
    news_results = news.fetch_for_markets([question])
    news_context = str(news_results.get(question, [])[:5])

    current_prices = {k: v for k, v in price_map.items() if v is not None}
    llm_out = llm.reason(
        market_context=question,
        news_context=news_context,
        current_prices=current_prices,
    )
    edge_out = edge.size(llm_out, market_price_yes)

    # 3) Execution Layer: sync positions, optionally place order
    position_tracker.sync_positions()

    if edge_out.get("suggested_action") in ("buy_yes", "buy_no") and edge_out.get("kelly_fraction", 0) > 0.01:
        side = "BUY"
        outcome = "Yes" if edge_out["suggested_action"] == "buy_yes" else "No"
        size = 10.0 * edge_out["kelly_fraction"]  # scale by budget
        price = market_price_yes if outcome == "Yes" else (1.0 - market_price_yes)
        token_id = token_ids[0] if token_ids else None
        order_manager.place_order(
            market_id=condition_id,
            outcome=outcome,
            side=side,
            size=size,
            price=price,
            token_id=token_id,
        )


def main() -> None:
    interval_min = float(os.environ.get("ORCHESTRATOR_INTERVAL_MINUTES", "15"))
    db_path = Path(os.environ.get("STATE_DB_PATH", "state.db"))

    state_db = StateDB(db_path)
    markets = MarketsClient()
    orderbook = OrderbookClient()
    prices = PricesClient(orderbook)
    news = NewsFetcher()
    llm = LLMReasoner()
    edge = EdgeDetector(kelly_cap=0.25)
    wallet = WalletCLOB()
    order_manager = OrderManager(state_db, wallet)
    position_tracker = PositionTracker(state_db, wallet)

    print(f"Agent Orchestrator started (interval={interval_min} min). Ctrl+C to stop.")
    while True:
        try:
            run_one_cycle(
                state_db=state_db,
                markets=markets,
                orderbook=orderbook,
                prices=prices,
                news=news,
                llm=llm,
                edge=edge,
                order_manager=order_manager,
                position_tracker=position_tracker,
            )
        except Exception as e:
            print(f"Cycle error: {e}")
        time.sleep(interval_min * 60.0)


if __name__ == "__main__":
    main()
