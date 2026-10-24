"""Settings for DealScout: where the API key comes from, which model we use, what it costs, and the
hard limits that stop a run (or a user) from spending too much.

Secrets are never hard-coded, printed, or sent to the model."""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_DIR = PACKAGE_DIR.parent
DATA_DIR = REPO_DIR / "data"
DEMO_DIR = DATA_DIR / "demo_runs"
LOG_DIR = REPO_DIR / "logs"
CACHE_DIR = REPO_DIR / ".cache"


def _read_env_file(path: Path) -> None:
    """Load KEY=VALUE lines into os.environ without overwriting variables that are already set."""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def load_env() -> Path | None:
    """Look for .env first in the repo folder, then in the folder above it (where graders keep theirs)."""
    for folder in (REPO_DIR, REPO_DIR.parent):
        path = folder / ".env"
        if path.is_file():
            _read_env_file(path)
            return path
    return None


ENV_FILE = load_env()


def portkey_key() -> str:
    return os.getenv("PORTKEY_API_KEY", "").strip()


PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
PORTKEY_PROVIDER = "openai"

# The course key may only be used with this model, so it is fixed here on purpose (not read from env).
MODEL = "gpt-6-luna"

# Prices in US dollars (course Lecture 11 price sheet for gpt-6-luna; OpenAI web search tool fee).
PRICE_PER_M = {"input": 0.10, "cached_input": 0.01, "cache_write": 0.125, "output": 0.50}
WEB_SEARCH_FEE = 0.010  # $10 per 1,000 web_search calls

# ---- Spending and loop limits ----
MAX_SEARCHES_SCOUT = 8           # web searches the Scout may run in one hunt
MAX_SEARCHES_CHECKER = 6         # web searches the Fact-Checker may run in one hunt
MAX_TOOL_ROUNDS = 4              # function-tool round trips per agent call (stops loops)
MAX_DEALS = 8                    # deals the Scout may return
RUN_TOKEN_CAP = 250_000          # input + output tokens for one whole run, all agents combined
RUN_COST_CAP = 0.25              # dollars for one run
DAILY_COST_CAP = float(os.getenv("DEALSCOUT_DAILY_BUDGET", "2.00"))  # dollars per day, whole app
RUNS_PER_10_MIN = 6              # live hunts allowed per browser session per 10 minutes
CACHE_TTL_HOURS = 24             # how long a saved hunt is reused for an identical request
CALL_DEADLINE_S = 120            # hard wall-clock limit for one model call (a hung call can't freeze the app)

# SEC asks automated tools to identify themselves. Override with your own contact in .env if you like.
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "DealScout student research app (contact: dealscout@example.com)")

for _d in (LOG_DIR, CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)
