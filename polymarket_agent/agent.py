"""
Main entry point: run agent loop every N minutes.
  data → analysis (news → LLM → edge) → execution (risk → trade) → state
"""
import json
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from config import ORCHESTRATOR_INTERVAL_MINUTES
from state.database import Database
from data.market_fetcher import MarketFetcher
from data.news_fetcher import NewsFetcher
from analysis.llm_reasoner import LLMReasoner
from analysis.edge_detector import EdgeDetector
from execution.trade_executor import TradeExecutor
from execution.risk_manager import RiskManager

console = Console()


def _token_ids(market: dict) -> list[str]:
    """Extract CLOB token IDs from a Gamma market payload."""
    clob = market.get("clobTokenIds")
    if clob:
        if isinstance(clob, str):
            try:
                return json.loads(clob)
            except Exception:
                return [clob]
        if isinstance(clob, list):
            return clob
    return []


def _analyze_market(
    m: dict,
    idx: int,
    total: int,
    markets: MarketFetcher,
    news: NewsFetcher,
    llm: LLMReasoner,
    edge: EdgeDetector,
) -> dict | None:
    """Analyze one market; return opportunity dict or None."""
    condition_id = m.get("conditionId") or m.get("condition_id") or ""
    question = m.get("question", "")
    token_ids = _token_ids(m)
    if not token_ids:
        return None

    console.print(f"  [blue][{idx + 1}/{total}][/blue] [bold]{question[:70]}{'…' if len(question) > 70 else ''}[/bold]")

    price_map = markets.get_prices(token_ids)
    market_price_yes = next((p for p in price_map.values() if p is not None), None)
    if market_price_yes is None:
        console.print(f"      [yellow]Warning: No price available, skipping[/yellow]")
        return None
    news_results = news.fetch_for_markets([question])
    news_context = str(news_results.get(question, [])[:5])
    current_prices = {k: v for k, v in price_map.items() if v is not None}

    llm_out = llm.reason(
        market_context=question,
        news_context=news_context,
        current_prices=current_prices,
    )
    edge_out = edge.size(llm_out, market_price_yes)
    action = edge_out.get("suggested_action")
    kelly = edge_out.get("kelly_fraction", 0) or 0

    console.print(f"      [dim]price_yes={market_price_yes:.3f}  edge={edge_out.get('edge', 0):.3f}  kelly={kelly:.3f}  → {action or 'no_trade'}[/dim]")

    return {
        "market": m,
        "condition_id": condition_id,
        "question": question,
        "token_ids": token_ids,
        "market_price_yes": market_price_yes,
        "llm_out": llm_out,
        "edge_out": edge_out,
        "action": action,
        "kelly": kelly,
    }


def run_one_cycle(traded_markets=traded_markets, traded_markets: dict = None,
    
    db: Database,
    markets: MarketFetcher,
    news: NewsFetcher,
    llm: LLMReasoner,
    edge: EdgeDetector,
    executor: TradeExecutor,
    risk: RiskManager,
    max_markets: int = 100,
    traded_markets: dict = None,
) -> None:
    if traded_markets is None: traded_markets = {}
    """Single cycle: fetch all markets → analyze each → pick best edge → risk-check → execute once."""
    console.print()
    console.print("[bold cyan]── Fetching markets[/bold cyan]")
    from datetime import datetime, timezone
    market_list_raw = markets.get_markets(limit=200, closed=False)
    now = datetime.now(timezone.utc)
    market_list = []
    for m in market_list_raw:
        end_date = m.get("endDate") or m.get("end_date") or ""
        if end_date:
            try:
                ed = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                days_left = (ed - now).days
                if days_left < 0 or days_left > 90:
                    continue
            except Exception:
                pass
        # skip if already have open position in this market
        cid = m.get("conditionId") or ""
        try:
            all_orders = executor._get_clob_client().get_orders() or []
            existing_orders = [o for o in all_orders if (o.get('market') or o.get('asset_id') or '') == cid]
            if len(existing_orders) >= 2:
                continue
        except Exception:
            pass
        market_list.append(m)
    market_list = market_list[:max_markets]
    if not market_list:
        console.print("[yellow]No markets returned.[/yellow]")
        return
    console.print(f"[green]Fetched {len(market_list)} market(s)[/green]")

    console.print("[bold cyan]── Analyzing all markets[/bold cyan]")
    opportunities: list[dict] = []
    for i, m in enumerate(market_list):
        try:
            opp = _analyze_market(m, i, len(market_list), markets, news, llm, edge)
            if opp and opp["action"] in ("buy_yes", "buy_no") and (opp["kelly"] or 0) > 0.01:
                opportunities.append(opp)
        except Exception as e:
            console.print(f"  [red]Error analyzing market: {e}[/red]")

    executor.sync_positions()

    if not opportunities:
        console.print(
            Panel(
                "[yellow]No tradeable opportunity with edge above threshold (Kelly > 0.01).[/yellow]",
                title="[bold yellow]Trade skipped[/bold yellow]",
                border_style="yellow",
                box=box.ROUNDED,
            )
        )
        return

    # Best opportunity = highest edge * kelly (want both edge and size)
    best = max(opportunities, key=lambda o: (o["edge_out"].get("edge", 0) or 0) * (o["kelly"] or 0))
    condition_id = best["condition_id"]
    question = best["question"]
    token_ids = best["token_ids"]
    market_price_yes = best["market_price_yes"]
    action = best["action"]
    kelly = best["kelly"]
    llm_out = best["llm_out"]
    edge_out = best["edge_out"]

    console.print(Panel(
        f"[bold]{question[:80]}{'…' if len(question) > 80 else ''}[/bold]\n\n"
        f"Edge: [bold]{edge_out.get('edge', 0):.4f}[/bold]  Kelly: [bold]{kelly:.4f}[/bold]  Action: [bold]{action}[/bold]\n"
        f"Thesis: [dim]{llm_out.get('thesis', '') or '(none)'}[/dim]",
        title="[bold green]Best opportunity[/bold green]",
        border_style="green",
        box=box.ROUNDED,
    ))

    outcome = "Yes" if action == "buy_yes" else "No"
    price = market_price_yes if outcome == "Yes" else (1.0 - market_price_yes)
    size = max(10.0, 20.0 * kelly)
    size = risk.capped_size(size, price)

    allowed, reason = risk.approve_trade(condition_id, outcome, size, price)
    if not allowed:
        console.print(
            Panel(
                f"[red]{reason}[/red]",
                title="[bold red]Trade skipped (risk)[/bold red]",
                border_style="red",
                box=box.ROUNDED,
            )
        )
        return

    console.print(
        Panel(
            f"market_id: [dim]{condition_id}[/dim]\noutcome: [bold]{outcome}[/bold]  side: BUY  size: {size:.4f}  price: {price:.4f}",
            title="[bold green]Placing trade[/bold green]",
            border_style="green",
            box=box.ROUNDED,
        )
    )
    _cid = best["market"].get("conditionId","") if best else ""
    if traded_markets.get(_cid, 0) >= 2:
        console.print("  [yellow]Skipping: max 2 trades reached for this market[/yellow]")
    else:
     result = executor.place_order(
        market_id=condition_id,
        outcome=outcome,
        side="BUY",
        size=size,
        price=price,
        token_id=(token_ids[1] if action == "buy_no" and len(token_ids) > 1 else token_ids[0]) if token_ids else None,
    )
    console.print(f"  [dim]Result: {result}[/dim]")
    traded_markets[_cid] = traded_markets.get(_cid, 0) + 1


def main() -> None:
    db = Database()
    markets = MarketFetcher()
    traded_markets: dict = {}
    news = NewsFetcher()
    llm = LLMReasoner()
    edge = EdgeDetector()
    executor = TradeExecutor(db)
    risk = RiskManager(db)

    console.print(
        Panel(
            f"Interval: [bold]{ORCHESTRATOR_INTERVAL_MINUTES}[/bold] min\n\n[dim]Ctrl+C to stop.[/dim]",
            title="[bold green]Polymarket agent started[/bold green]",
            border_style="green",
            box=box.ROUNDED,
        )
    )
    while True:
        try:
            run_one_cycle(traded_markets=traded_markets, db, markets, news, llm, edge, executor, risk)
        except Exception as e:
            console.print(f"[bold red]Cycle error:[/bold red] {e}", style="red")
        time.sleep(ORCHESTRATOR_INTERVAL_MINUTES * 60.0)


if __name__ == "__main__":
    main()
