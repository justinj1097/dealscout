"""The orchestrator. Plain Python decides who works next, so no agent can hand itself extra power:

    user form -> input guard -> cache? -> Scout -> Gatekeeper (code) -> Fact-Checker
              -> score_deals (code) -> Analyst -> results          ...later, on click: Pitch Coach

Every step is written to a trace the app shows, every model call to the token ledger, and every
safety catch to the safety log."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from urllib.parse import urlparse

from . import agents, config, safety, tools
from .ledger import BudgetExceeded, Ledger
from .models import AnalystReport, CheckReport, Criteria

_recent_runs: dict[str, deque] = defaultdict(deque)


class RateLimited(RuntimeError):
    pass


_all_runs: deque = deque()


def _rate_limit(visitor: str) -> None:
    """Two limits: one visitor (IP address) gets RUNS_PER_10_MIN live searches per 10 minutes, and the
    whole app gets RUNS_PER_HOUR_APP per hour, so a stranger on the public link can't run up the bill."""
    now = time.time()
    while _all_runs and now - _all_runs[0] > 3600:
        _all_runs.popleft()
    if len(_all_runs) >= config.RUNS_PER_HOUR_APP:
        raise RateLimited("DealScout is busy: the app-wide limit of live searches per hour is reached. "
                          "Try a saved example, or come back in a few minutes.")
    q = _recent_runs[visitor]
    while q and now - q[0] > 600:
        q.popleft()
    if len(q) >= config.RUNS_PER_10_MIN:
        wait = int(600 - (now - q[0])) // 60 + 1
        raise RateLimited(f"Slow down: {config.RUNS_PER_10_MIN} live searches per 10 minutes. Try again in about {wait} min, "
                          "or re-run a previous search (saved searches are free).")
    q.append(now)
    _all_runs.append(now)


def _cache_key(c: Criteria) -> str:
    raw = json.dumps(c.model_dump(), sort_keys=True).lower()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _cache_get(key: str) -> dict | None:
    f = config.CACHE_DIR / f"hunt_{key}.json"
    if not f.is_file():
        return None
    data = json.loads(f.read_text())
    if time.time() - data.get("saved_at", 0) > config.CACHE_TTL_HOURS * 3600:
        return None
    return data


def _host(u: str) -> str:
    return urlparse(u or "").netloc.lower().removeprefix("www.")


def _date_ok(d: str, months_back: int) -> bool:
    for fmt, n in (("%Y-%m-%d", 10), ("%Y-%m", 7)):
        try:
            when = datetime.strptime((d or "")[:n], fmt)
            return datetime.now() - timedelta(days=30.5 * (months_back + 1)) <= when <= datetime.now() + timedelta(days=2)
        except ValueError:
            continue
    return False


def gatekeeper(raw: list[dict], c: Criteria, scout_res, log: safety.SafetyLog) -> tuple[list[dict], list[dict]]:
    """Code-only checks between the Scout and everyone else. Returns (kept, rejected)."""
    kept, rejected, seen = [], [], set()
    for d in raw:
        where = f"{d.get('acquirer', '?')} / {d.get('target', '?')}"
        for f in ("acquirer", "target", "deal_type", "status", "source_title"):
            d[f] = safety.clean_untrusted(str(d.get(f, "")), f, where, log, limit=120)
        for f in ("value_quote", "multiple_quote", "strategic_rationale"):
            d[f] = safety.clean_untrusted(str(d.get(f, "")), f, where, log, limit=400)
        for f in ("buyer_advisors", "seller_advisors"):
            d[f] = [safety.clean_untrusted(b, f, where, log, limit=80) for b in d.get(f, [])][:6]
            d[f] = [b for b in d[f] if not b.startswith("[removed")]
        key = (d["acquirer"].lower()[:20], d["target"].lower()[:20])
        reason = None
        if "[removed" in d["acquirer"] + d["target"]:
            reason = "company name contained an injection attempt"
        elif not safety.url_was_searched(d.get("source_url", ""), scout_res.searched_urls, scout_res.tool_urls):
            reason = "its source link never appeared in any search result (possible made-up link)"
            log.add("fake link blocked", where, f"{d.get('source_url', '')[:120]} was not in the search results")
        elif key in seen:
            reason = "duplicate"
        elif d["acquirer"].lower() == d["target"].lower():
            reason = "buyer and target are the same"
        elif not _date_ok(d.get("announced_date", ""), c.months_back):
            reason = f"announced {d.get('announced_date') or 'on an unknown date'}, outside the last {c.months_back} months"
        if reason is None:
            ok, why = safety.quote_supports_value(d.get("value_usd_m"), d.get("value_quote", ""))
            if not ok:
                log.add("number not supported", where, f"Value removed: {why}")
                d["value_note"] = f"value removed – {why}"
                d["value_usd_m"] = None
            if d.get("value_usd_m") is not None and d["value_usd_m"] < c.min_value_usd_m * 0.97:
                reason = f"${d['value_usd_m']:,.0f}M is below your ${c.min_value_usd_m:,.0f}M minimum"
        if reason:
            rejected.append({"deal": where, "reason": reason})
            continue
        seen.add(key)
        kept.append(d)
    return kept, rejected


def _page_checks(deals: list[dict], log: safety.SafetyLog) -> None:
    def one(d):
        quote = d.get("value_quote") or d.get("strategic_rationale", "")[:80]
        d["page_check"], d["page_check_note"] = safety.fetch_and_match(d["source_url"], quote)
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(one, deals))
    for d in deals:
        if d["page_check"].startswith("page contains"):
            log.add("injection on source page", f"{d['acquirer']} / {d['target']}", d["page_check_note"])


def hunt(c: Criteria, session_id: str = "local", use_cache: bool = True, progress=None) -> dict:
    """Run the whole team for one request. Always returns a dict the UI can show (errors included)."""
    say = progress or (lambda msg: None)
    t0 = time.time()
    log = safety.SafetyLog()
    run_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    ledger = Ledger(run_id)
    trace: list[dict] = []
    out = {"run_id": run_id, "criteria": c.model_dump(), "deals": [], "rejected": [], "trace": trace,
           "safety": [], "cached": False, "error": None, "theme": "", "notes": ""}

    safe_note = safety.check_user_note(c.note, log)
    c = c.model_copy(update={"note": safe_note})
    trace.append({"agent": "Input guard (code)", "steps": [
        f"criteria: {c.industry} | ≥ ${c.min_value_usd_m:,.0f}M | last {c.months_back} months | {c.region} | {c.priority}",
        "free-text note: " + ("blocked (see Safety tab)" if c.note == "" and log.events else (f"“{c.note}”" if c.note else "none"))]})

    key = _cache_key(c)
    if use_cache and (hit := _cache_get(key)):
        hit.update({"cached": True, "run_id": run_id, "safety": [vars(e) for e in log.events] + hit.get("safety", [])})
        hit["trace"] = trace + [{"agent": "Cache", "steps": [f"identical search from {hit.get('saved_time', '?')} reused – 0 tokens, $0.00"]}]
        hit["usage"] = {"by_agent": [], "totals": {"input_tokens": 0, "cached_tokens": 0, "cache_write_tokens": 0,
                        "output_tokens": 0, "reasoning_tokens": 0, "web_searches": 0, "cost": 0.0, "seconds": 0.0}}
        ledger.save({"cached": True, "industry": c.industry})
        return hit

    try:
        _rate_limit(session_id)
        say("Scout is searching the web and SEC filings…")
        s = agents.scout(ledger, c, safe_note)
        raw = [d.model_dump() for d in s.parsed.deals][: config.MAX_DEALS]
        out["notes"] = s.parsed.search_notes
        trace.append({"agent": "Scout", "steps": s.steps + [f"returned {len(raw)} candidate deals"]})

        say("Gatekeeper is checking links and numbers…")
        deals, rejected = gatekeeper(raw, c, s, log)
        _page_checks(deals, log)
        out["rejected"] = rejected
        trace.append({"agent": "Gatekeeper (code)", "steps":
                      [f"kept {len(deals)}, rejected {len(rejected)}"] +
                      [f"✗ {r['deal']}: {r['reason']}" for r in rejected] +
                      [f"source page {d['page_check']}: {d['acquirer']} / {d['target']} ({d['page_check_note']})" for d in deals]})
        if not deals:
            out["error"] = "No deals passed the checks. Try a lower minimum size, a longer time window, or a broader industry."
            return _finish(out, ledger, log, t0)

        say("Fact-Checker is confirming each deal with a second source…")
        try:
            fc = agents.fact_checker(ledger, deals)
        except (agents.AgentTimeout, BudgetExceeded) as e:  # degrade, don't fail: show deals as unconfirmed
            log.add("agent stopped", "Fact-Checker", f"{e} Deals are shown as 'not independently confirmed'.")
            fc = agents.AgentResult(parsed=CheckReport(checks=[]), steps=[f"⚠ stopped: {e}"])
        checks = {ck.deal_index: ck for ck in fc.parsed.checks}
        for i, d in enumerate(deals):
            ck = checks.get(i)
            d["verdict"] = ck.verdict if ck else "could not confirm"
            d["check_note"] = safety.clean_untrusted(ck.note if ck else "not checked (search budget)", "check note", d["target"], log, 200)
            ind = ck.independent_source_url if ck else ""
            good = ind and _host(ind) != _host(d["source_url"]) and safety.url_was_searched(ind, fc.searched_urls, set())
            if ind and not good:
                log.add("fake link blocked", f"{d['acquirer']} / {d['target']}", "Fact-Checker's second source was not a new search result; dropped")
            d["second_source"] = ind if good else ""
            if ck and good and not (d["buyer_advisors"] or d["seller_advisors"]):
                d["buyer_advisors"] = [safety.clean_untrusted(b, "advisor", d["target"], log, 80) for b in ck.buyer_advisors_found][:5]
                d["seller_advisors"] = [safety.clean_untrusted(b, "advisor", d["target"], log, 80) for b in ck.seller_advisors_found][:5]
                if d["buyer_advisors"] or d["seller_advisors"]:
                    d["advisors_source"] = ind
            if d["verdict"] == "confirmed" and not good:
                d["verdict"] = "partly confirmed"  # a confirmation needs a real, different source
            if ck and ck.confirmed_value_usd_m and d.get("value_usd_m") and \
                    abs(ck.confirmed_value_usd_m - d["value_usd_m"]) > 0.05 * d["value_usd_m"]:
                d["verdict"] = "conflict"
        trace.append({"agent": "Fact-Checker", "steps": fc.steps + [f"{d['target']}: {d['verdict']} – {d['check_note']}" for d in deals]})

        deals = tools.score_deals(deals, c.priority, c.months_back)
        deals = [d for d in deals if d["verdict"] != "conflict"] + [d for d in deals if d["verdict"] == "conflict"]
        deals = deals[: c.num_deals]
        trace.append({"agent": "score_deals tool (code)", "steps": [f"{d['score']:>5} – {d['acquirer']} / {d['target']}" for d in deals]})

        say("Analyst is writing why each deal matters…")
        try:
            an = agents.analyst(ledger, c, deals)
        except (agents.AgentTimeout, BudgetExceeded) as e:
            log.add("agent stopped", "Analyst", f"{e} Showing the Scout's rationale instead.")
            an = agents.AgentResult(parsed=AnalystReport(takes=[], industry_theme=""), steps=[f"⚠ stopped: {e}"])
        for t in an.parsed.takes:
            if 0 <= t.deal_index < len(deals):
                d = deals[t.deal_index]
                d["why_it_matters"] = safety.clean_untrusted(t.why_it_matters, "why_it_matters", d["target"], log, 300)
                d["interview_angle"] = safety.clean_untrusted(t.interview_angle, "interview_angle", d["target"], log, 300)
        out["theme"] = safety.clean_untrusted(an.parsed.industry_theme, "theme", "Analyst", log, 300)
        trace.append({"agent": "Analyst", "steps": an.steps})

        out["deals"] = deals
        tools.add_to_library(c.industry, deals)
        out["saved_at"], out["saved_time"] = time.time(), time.strftime("%b %d %H:%M")
        result = _finish(out, ledger, log, t0)
        (config.CACHE_DIR / f"hunt_{key}.json").write_text(json.dumps(result))
        return result
    except (BudgetExceeded, RateLimited, agents.AgentTimeout) as e:
        kind = {BudgetExceeded: "budget stop", RateLimited: "rate limit"}.get(type(e), "agent stopped")
        log.add(kind, "orchestrator", str(e))
        out["error"] = str(e)
    except agents.MissingKey as e:
        out["error"] = str(e)
    except Exception as e:  # never show a stack trace (or a secret) to the user
        out["error"] = f"Something went wrong ({type(e).__name__}). Please try again."
        out["debug"] = safety.redact(str(e))[:300]
    return _finish(out, ledger, log, t0)


def _finish(out: dict, ledger: Ledger, log: safety.SafetyLog, t0: float) -> dict:
    out["safety"] = [vars(e) for e in log.events]
    out["usage"] = {"by_agent": ledger.by_agent(), "totals": ledger.totals()}
    out["elapsed"] = round(time.time() - t0, 1)
    ledger.save({"industry": out["criteria"]["industry"], "deals": len(out["deals"]), "error": out["error"],
                 "safety_events": len(out["safety"])})
    return out


def pitch(industry: str, deal: dict, session_id: str = "local") -> dict:
    key = hashlib.sha256(f"{deal['acquirer']}|{deal['target']}".lower().encode()).hexdigest()[:16]
    f = config.CACHE_DIR / f"pitch_{key}.json"
    if f.is_file():
        data = json.loads(f.read_text())
        data.update(cached=True, usage={"totals": {"input_tokens": 0, "cached_tokens": 0, "output_tokens": 0,
                                                     "cost": 0.0, "web_searches": 0}})
        return data
    log = safety.SafetyLog()
    ledger = Ledger("pitch-" + time.strftime("%Y%m%d-%H%M%S"))
    try:
        r = agents.pitch_coach(ledger, industry, deal)
        p = r.parsed.model_dump()
        p["sixty_second_pitch"] = safety.clean_untrusted(p["sixty_second_pitch"], "pitch", deal["target"], log, 1500)
        data = {"pitch": p, "steps": r.steps, "cached": False, "error": None}
    except (BudgetExceeded, agents.MissingKey, agents.AgentTimeout) as e:
        data = {"pitch": None, "steps": [], "cached": False, "error": str(e)}
    except Exception as e:
        data = {"pitch": None, "steps": [], "cached": False, "error": f"Pitch failed ({type(e).__name__}). Try again."}
    data["usage"] = {"totals": ledger.totals(), "by_agent": ledger.by_agent()}
    data["safety"] = [vars(e) for e in log.events]
    ledger.save({"pitch_for": f"{deal['acquirer']} / {deal['target']}"})
    if data["pitch"]:
        f.write_text(json.dumps(data))
    return data
