"""
Central config from environment.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# API keys
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
TAVILY_API_KEY = env("TAVILY_API_KEY")
POLYMARKET_API_KEY = env("POLYMARKET_API_KEY")
POLYMARKET_SECRET = env("POLYMARKET_SECRET")
POLYMARKET_PRIVATE_KEY = env("POLYMARKET_PRIVATE_KEY")

# Orchestrator
ORCHESTRATOR_INTERVAL_MINUTES = float(env("ORCHESTRATOR_INTERVAL_MINUTES", "2"))
STATE_DB_PATH = Path(env("STATE_DB_PATH", "state.db"))

# LLM
LLM_MODEL = env("LLM_MODEL", "claude-sonnet-4-20250514")

# Risk (optional overrides)
KELLY_CAP = float(env("KELLY_CAP", "0.10"))
MAX_POSITION_SIZE = float(env("MAX_POSITION_SIZE", "100"))
MAX_DAILY_LOSS = float(env("MAX_DAILY_LOSS", "500"))

# Trading mode
PAPER_TRADING = env("PAPER_TRADING", "false").lower() in ("true", "1", "yes")

# Polygon RPC (for USDC balance via Web3)
POLYGON_RPC_URL = env("POLYGON_RPC_URL", "https://polygon-rpc.com")
