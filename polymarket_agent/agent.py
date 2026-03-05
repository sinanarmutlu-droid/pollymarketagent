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
    console.print()
    console.print("[bold cyan]── Fetching markets[/bold cyan]")
    market_list = markets.get_markets(limit=max_markets, closed=False)
    if not market_list:
        console.print("[yellow]No markets returned.[/yellow]")
        return
    console.print(f"[green]Fetched {len(market_list)} market(s)[/green]")

    m = market_list[0]
    condition_id = m.get("conditionId") or m.get("condition_id") or ""
    question = m.get("question", "")
    token_ids = _token_ids(m)

    console.print(Panel(
        f"[bold]{question}[/bold]\n\ncondition_id: [dim]{condition_id}[/dim]\ntoken_ids: [dim]{len(token_ids)} token(s)[/dim]",
        title="[bold blue]Analyzing market[/bold blue]",
        border_style="blue",
        box=box.ROUNDED,
    ))

    price_map = markets.get_prices(token_ids) if token_ids else {}
    market_price_yes = next((p for p in price_map.values() if p is not None), 0.5) or 0.5
    console.print(f"  [dim]Market price (Yes): {market_price_yes:.4f}[/dim]")

    news_results = news.fetch_for_markets([question])
    news_context = str(news_results.get(question, [])[:5])
    current_prices = {k: v for k, v in price_map.items() if v is not None}

    console.print("[bold cyan]── LLM reasoning[/bold cyan]")
    llm_out = llm.reason(
        market_context=question,
        news_context=news_context,
        current_prices=current_prices,
    )
    llm_table = Table(show_header=False, box=box.SIMPLE)
    llm_table.add_column("Key", style="cyan")
    llm_table.add_column("Value", style="white")
    llm_table.add_row("Thesis", llm_out.get("thesis", "") or "(none)")
    llm_table.add_row("Confidence", str(llm_out.get("confidence_0_1", 0)))
    llm_table.add_row("Direction", llm_out.get("direction", "—"))
    llm_table.add_row("Reasoning", llm_out.get("reasoning", "") or "(none)")
    console.print(Panel(llm_table, title="[bold]LLM decision[/bold]", border_style="magenta", box=box.ROUNDED))

    edge_out = edge.size(llm_out, market_price_yes)
    console.print(f"  [dim]Edge: {edge_out.get('edge', 0):.4f}  Kelly fraction: {edge_out.get('kelly_fraction', 0):.4f}  Action: {edge_out.get('suggested_action', '—')}[/dim]")

    executor.sync_positions()

    action = edge_out.get("suggested_action")
    kelly = edge_out.get("kelly_fraction", 0) or 0
    if action not in ("buy_yes", "buy_no") or kelly <= 0.01:
        console.print(
            Panel(
                f"[yellow]Action: [bold]{action or 'no_trade'}[/bold]\nKelly: {kelly:.4f}[/yellow]\n\n[dim]Skipping: no trade signal or Kelly below threshold (0.01).[/dim]",
                title="[bold yellow]Trade skipped[/bold yellow]",
                border_style="yellow",
                box=box.ROUNDED,
            )
        )
        return

    outcome = "Yes" if action == "buy_yes" else "No"
    price = market_price_yes if outcome == "Yes" else (1.0 - market_price_yes)
    size = 10.0 * kelly
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
    result = executor.place_order(
        market_id=condition_id,
        outcome=outcome,
        side="BUY",
        size=size,
        price=price,
        token_id=token_ids[0] if token_ids else None,
    )
    console.print(f"  [dim]Result: {result}[/dim]")


def main() -> None:
    db = Database()
    markets = MarketFetcher()
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
            run_one_cycle(db, markets, news, llm, edge, executor, risk)
        except Exception as e:
            console.print(f"[bold red]Cycle error:[/bold red] {e}", style="red")
        time.sleep(ORCHESTRATOR_INTERVAL_MINUTES * 60.0)


if __name__ == "__main__":
    main()
