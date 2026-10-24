"""Tools the agents can use, plus the deal library.

- edgar_search      (Scout)        free SEC EDGAR full-text search for merger filings
- web_search        (Scout, Fact-Checker)  OpenAI's hosted search tool, capped per call
- score_deals       (Analyst)      transparent scoring formula, no model involved
- get_comparables   (Pitch Coach)  similar deals from the local deal library, with median value
"""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timedelta
from statistics import median

import requests

from . import config

# ---------------------------------------------------------------- SEC EDGAR full-text search
EDGAR_URL = "https://efts.sec.gov/LATEST/search-index"

EDGAR_TOOL = {
    "type": "function",
    "name": "edgar_search",
    "description": ("Search official SEC EDGAR filings (8-K, 425, S-4, DEFM14A) for merger and acquisition "
                    "announcements by U.S.-listed companies. Use short keyword queries such as "
                    "'aerospace merger agreement' or a company name. Returns filer, form, date, and link."),
    "parameters": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Keywords, e.g. 'defense acquisition agreement'"}},
        "required": ["query"],
        "additionalProperties": False,
    },
    "strict": True,
}


def edgar_search(query: str, months_back: int = 12, limit: int = 8) -> dict:
    query = re.sub(r"[^\w\s&\-'.]", " ", query)[:120].strip()
    start = (date.today() - timedelta(days=30 * months_back)).isoformat()
    params = {"q": query, "forms": "8-K,425,S-4,DEFM14A", "dateRange": "custom",
              "startdt": start, "enddt": date.today().isoformat()}
    try:
        r = requests.get(EDGAR_URL, params=params, headers={"User-Agent": config.SEC_USER_AGENT}, timeout=15)
        r.raise_for_status()
        hits = r.json().get("hits", {}).get("hits", [])
    except (requests.RequestException, ValueError) as e:
        return {"error": f"EDGAR unavailable ({type(e).__name__})", "results": []}
    out, seen = [], set()
    for h in hits:
        s = h.get("_source", {})
        adsh, _, fname = h.get("_id", "").partition(":")
        ciks = s.get("ciks") or []
        if not adsh or not ciks:
            continue
        key = (adsh, s.get("display_names", [""])[0])
        if key in seen:
            continue
        seen.add(key)
        cik = str(int(ciks[0]))
        out.append({
            "company": (s.get("display_names") or ["?"])[0],
            "form": s.get("form") or s.get("root_forms", ["?"])[0],
            "filed": s.get("file_date"),
            "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/{fname}",
        })
        if len(out) >= limit:
            break
    return {"results": out}


# ---------------------------------------------------------------- scoring (Analyst tool)
BULGE = {"goldman", "morgan stanley", "j.p. morgan", "jp morgan", "jpmorgan", "bofa", "bank of america",
         "citi", "barclays", "deutsche", "ubs", "wells fargo"}
ELITE = {"evercore", "centerview", "lazard", "pjt", "moelis", "perella", "guggenheim", "qatalyst",
         "rothschild", "jefferies", "houlihan", "raymond james", "rbc"}
VERDICT_SCORE = {"confirmed": 1.0, "partly confirmed": 0.7, "could not confirm": 0.35, "conflict": 0.0}

WEIGHTS = {  # how much each factor counts, by what the user said they care about
    "Biggest deals":       {"size": .50, "recency": .10, "banks": .10, "multiple": .05, "trust": .25},
    "Most recent":         {"size": .15, "recency": .50, "banks": .05, "multiple": .05, "trust": .25},
    "Most talked-about":   {"size": .30, "recency": .20, "banks": .20, "multiple": .05, "trust": .25},
    "Best for interviews": {"size": .25, "recency": .20, "banks": .15, "multiple": .15, "trust": .25},
}


def _months_ago(d: str) -> float:
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return max((datetime.now() - datetime.strptime(d[:len(fmt) + 2], fmt)).days / 30.4, 0)
        except ValueError:
            continue
    return 12.0


def bank_tier(names: list[str]) -> float:
    low = " ".join(names).lower()
    if any(b in low for b in BULGE):
        return 1.0
    if any(b in low for b in ELITE):
        return 0.8
    return 0.3 if names else 0.0


def score_deals(deals: list[dict], priority: str, months_back: int) -> list[dict]:
    w = WEIGHTS.get(priority, WEIGHTS["Best for interviews"])
    for d in deals:
        v = d.get("value_usd_m") or 0
        parts = {
            "size": min(math.log10(v + 1) / math.log10(50_001), 1.0) if v else 0.0,
            "recency": max(1 - _months_ago(d.get("announced_date", "")) / max(months_back, 1), 0.0),
            "banks": bank_tier(d.get("buyer_advisors", []) + d.get("seller_advisors", [])),
            "multiple": 1.0 if (d.get("ev_ebitda") or d.get("ev_revenue")) else 0.0,
            "trust": VERDICT_SCORE.get(d.get("verdict", "could not confirm"), 0.35),
        }
        d["score"] = round(100 * sum(w[k] * parts[k] for k in w), 1)
        d["score_parts"] = {k: round(v2, 2) for k, v2 in parts.items()}
    return sorted(deals, key=lambda d: d["score"], reverse=True)


# ---------------------------------------------------------------- deal library (Pitch Coach tool)
LIBRARY = config.DATA_DIR / "deal_library.json"


def _load_library() -> list[dict]:
    try:
        return json.loads(LIBRARY.read_text())
    except (OSError, ValueError):
        return []


def add_to_library(industry: str, deals: list[dict]) -> None:
    lib = _load_library()
    known = {(x["acquirer"].lower(), x["target"].lower()) for x in lib}
    for d in deals:
        if d.get("verdict") in ("confirmed", "partly confirmed") and (d["acquirer"].lower(), d["target"].lower()) not in known:
            lib.append({k: d.get(k) for k in ("acquirer", "target", "announced_date", "value_usd_m", "ev_ebitda",
                                               "ev_revenue", "deal_type", "source_url")} | {"industry": industry})
    LIBRARY.write_text(json.dumps(lib, indent=1))


COMPARABLES_TOOL = {
    "type": "function",
    "name": "get_comparables",
    "description": "Look up other verified deals in the same industry from DealScout's deal library, with the median deal size and multiples.",
    "parameters": {
        "type": "object",
        "properties": {"industry": {"type": "string"}, "exclude_target": {"type": "string"}},
        "required": ["industry", "exclude_target"],
        "additionalProperties": False,
    },
    "strict": True,
}


def get_comparables(industry: str, exclude_target: str) -> dict:
    key = industry.lower().split()[0] if industry else ""
    rows = [d for d in _load_library()
            if key and key in (d.get("industry") or "").lower() and d["target"].lower() != exclude_target.lower()]
    rows = sorted(rows, key=lambda d: d.get("announced_date") or "", reverse=True)[:6]
    vals = [d["value_usd_m"] for d in rows if d.get("value_usd_m")]
    ebitda = [d["ev_ebitda"] for d in rows if d.get("ev_ebitda")]
    return {
        "comparables": [{k: d.get(k) for k in ("acquirer", "target", "announced_date", "value_usd_m", "ev_ebitda")} for d in rows],
        "median_value_usd_m": median(vals) if vals else None,
        "median_ev_ebitda": median(ebitda) if ebitda else None,
    }
