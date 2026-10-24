"""Does cutting the web-search budget save money without hurting results? Runs the same searches with a
lean and the default budget (no result cache) and records cost and quality. Costs about $0.45 total.
Usage: python scripts/cost_experiment.py"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dealscout import config
from dealscout.models import Criteria
from dealscout.pipeline import hunt

CASES = [Criteria(industry="Aerospace & Defense", min_value_usd_m=500, months_back=12, num_deals=5),
         Criteria(industry="Technology / Software", min_value_usd_m=1000, months_back=12, num_deals=5),
         Criteria(industry="Healthcare & Biotech", min_value_usd_m=1000, months_back=12, num_deals=5)]
BUDGETS = {"lean (Scout 4 / Checker 3)": (4, 3), "default (Scout 8 / Checker 6)": (8, 6)}
rows = []
for label, (s, c) in BUDGETS.items():
    config.MAX_SEARCHES_SCOUT, config.MAX_SEARCHES_CHECKER = s, c
    for crit in CASES:
        # a unique, harmless note makes every request new, so the Portkey gateway cannot replay an old answer
        crit = crit.model_copy(update={"note": f"comparison run {label[:4]} {time.strftime('%H%M%S')}"})
        h = hunt(crit, session_id=f"exp-{time.time()}", use_cache=False)
        t, d = h["usage"]["totals"], h["deals"]
        rows.append({"budget": label, "industry": crit.industry, "error": h["error"], "deals": len(d),
                     "confirmed": sum(x.get("verdict") == "confirmed" for x in d),
                     "with_banks": sum(bool(x.get("buyer_advisors") or x.get("seller_advisors")) for x in d),
                     "with_value": sum(x.get("value_usd_m") is not None for x in d),
                     "rejected": len(h["rejected"]), "safety_events": len(h["safety"]),
                     "input": t["input_tokens"], "cached": t["cached_tokens"], "output": t["output_tokens"],
                     "searches": t["web_searches"], "cost": round(t["cost"], 4), "seconds": h["elapsed"],
                     "gateway_cache_hits": t.get("gateway_cache_hits", 0)})
        print(rows[-1], flush=True)
(Path(__file__).resolve().parents[1] / "docs/evidence/cost_experiment.json").write_text(json.dumps(rows, indent=1))
