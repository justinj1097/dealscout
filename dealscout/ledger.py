"""Token ledger and spending guard.

Every model call is written down (agent, input / cached / cache-write / output / reasoning tokens,
web searches, dollars). Before each call the guard checks three limits: this run's tokens, this
run's dollars, and the whole app's dollars for today. If any is hit, the call never happens."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import date

from . import config


class BudgetExceeded(RuntimeError):
    """Raised before a model call that would break a spending limit."""


@dataclass
class CallRecord:
    agent: str
    input_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    web_searches: int = 0
    seconds: float = 0.0
    cost: float = 0.0


def call_cost(r: CallRecord) -> float:
    p = config.PRICE_PER_M
    fresh = max(r.input_tokens - r.cached_tokens - r.cache_write_tokens, 0)
    tokens = (fresh * p["input"] + r.cached_tokens * p["cached_input"]
              + r.cache_write_tokens * p["cache_write"] + r.output_tokens * p["output"]) / 1_000_000
    return tokens + r.web_searches * config.WEB_SEARCH_FEE


_day_lock = threading.Lock()


def _day_file():
    return config.LOG_DIR / f"spend_{date.today().isoformat()}.json"


def spent_today() -> float:
    f = _day_file()
    if not f.is_file():
        return 0.0
    try:
        return float(json.loads(f.read_text()).get("dollars", 0.0))
    except (ValueError, OSError):
        return 0.0


def _add_today(dollars: float) -> None:
    with _day_lock:
        total = spent_today() + dollars
        _day_file().write_text(json.dumps({"dollars": round(total, 6)}))


@dataclass
class Ledger:
    """One per run. Collects call records and enforces the per-run and per-day caps."""
    run_id: str
    token_cap: int = config.RUN_TOKEN_CAP
    cost_cap: float = config.RUN_COST_CAP
    daily_cap: float = config.DAILY_COST_CAP
    calls: list[CallRecord] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return sum(c.input_tokens + c.output_tokens for c in self.calls)

    @property
    def cost(self) -> float:
        return sum(c.cost for c in self.calls)

    def check(self, agent: str, worst_case_searches: int = 0) -> None:
        """Refuse to start a call if this run or today is already at a limit (or would be after the
        worst-case number of web searches this call is allowed)."""
        upcoming = worst_case_searches * config.WEB_SEARCH_FEE
        if self.tokens >= self.token_cap:
            raise BudgetExceeded(f"{agent}: run token cap reached ({self.tokens:,} of {self.token_cap:,}).")
        if self.cost + upcoming > self.cost_cap:
            raise BudgetExceeded(f"{agent}: run cost cap ${self.cost_cap:.2f} would be exceeded.")
        if spent_today() + upcoming > self.daily_cap:
            raise BudgetExceeded(f"{agent}: today's app budget ${self.daily_cap:.2f} is used up.")

    def add(self, rec: CallRecord) -> CallRecord:
        rec.cost = call_cost(rec)
        self.calls.append(rec)
        _add_today(rec.cost)
        return rec

    def by_agent(self) -> list[dict]:
        rows: dict[str, CallRecord] = {}
        for c in self.calls:
            r = rows.setdefault(c.agent, CallRecord(agent=c.agent))
            for k in ("input_tokens", "cached_tokens", "cache_write_tokens", "output_tokens",
                      "reasoning_tokens", "web_searches", "seconds", "cost"):
                setattr(r, k, getattr(r, k) + getattr(c, k))
        return [asdict(r) for r in rows.values()]

    def totals(self) -> dict:
        t = CallRecord(agent="TOTAL")
        for c in self.calls:
            for k in ("input_tokens", "cached_tokens", "cache_write_tokens", "output_tokens",
                      "reasoning_tokens", "web_searches", "seconds", "cost"):
                setattr(t, k, getattr(t, k) + getattr(c, k))
        return asdict(t)

    def save(self, extra: dict | None = None) -> None:
        line = {"run_id": self.run_id, "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "calls": [asdict(c) for c in self.calls], "totals": self.totals(), **(extra or {})}
        with (config.LOG_DIR / "token_log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
