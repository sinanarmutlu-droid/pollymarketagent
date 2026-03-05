# Agent Orchestrator (Polymarket)

Runs every **N minutes**, wiring:

- **Data Layer** → markets, orderbook, prices (Polymarket Gamma + CLOB)
- **Analysis Layer** → News (Tavily) → LLM (Claude) → Edge (Kelly sizing)
- **Execution Layer** → order management, position tracking, wallet/CLOB
- **State Layer** → SQLite (positions, trade log)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY, TAVILY_API_KEY (optional: POLYMARKET_API_KEY, POLYMARKET_SECRET)
```

## Run

```bash
# From repo root (so state.db and imports work)
export PYTHONPATH=.
python -m src.agent_orchestrator
```

Or set `ORCHESTRATOR_INTERVAL_MINUTES=15` (default) and `STATE_DB_PATH` if needed.

## Layout

```
Agent Orchestrator (runs every N minutes)
    ├── Data Layer      → Markets, Orderbook, Prices
    ├── Analysis Layer  → News Fetcher (Tavily) → LLM Reasoner (Claude) → Edge Detector (Kelly)
    ├── Execution Layer → Order mgmt, Position track, Wallet/CLOB
    └── State Layer     → SQLite DB (positions, trade_log)
```

- **State:** `src/state_layer/db.py` — SQLite schema and access.
- **Data:** `src/data_layer/` — Gamma markets, CLOB orderbook, derived prices.
- **Analysis:** `src/analysis_layer/` — Tavily search → Claude reasoning → Kelly fraction.
- **Execution:** `src/execution_layer/` — place/cancel orders, sync positions (stubs for live CLOB signing).
- **Orchestrator:** `src/agent_orchestrator.py` — one cycle: data → analyze → execute; loop every N min.

Without Polymarket API keys, execution is **paper-only** (trades logged to SQLite only).
