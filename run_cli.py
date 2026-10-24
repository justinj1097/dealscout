"""Run one DealScout search from the terminal (handy for testing and for the token log).
Example:  python run_cli.py "Aerospace & Defense" --min 500 --months 12"""
import argparse, json
from dealscout.models import Criteria
from dealscout.pipeline import hunt

p = argparse.ArgumentParser()
p.add_argument("industry")
p.add_argument("--focus", default="")
p.add_argument("--min", type=float, default=500)
p.add_argument("--months", type=int, default=12)
p.add_argument("--priority", default="Best for interviews")
p.add_argument("--n", type=int, default=5)
p.add_argument("--note", default="")
p.add_argument("--no-cache", action="store_true")
a = p.parse_args()
r = hunt(Criteria(industry=a.industry, focus=a.focus, min_value_usd_m=a.min, months_back=a.months,
                  priority=a.priority, num_deals=a.n, note=a.note), use_cache=not a.no_cache, progress=print)
for t in r["trace"]:
    print(f"\n== {t['agent']}"); [print("  ", s) for s in t["steps"]]
print("\nDEALS:")
for d in r["deals"]:
    print(f"  {d['score']:>5}  {d['acquirer']} -> {d['target']}  ${d.get('value_usd_m')}M  {d['announced_date']}  [{d['verdict']}]  banks={d['buyer_advisors']+d['seller_advisors']}")
print("SAFETY:", json.dumps(r["safety"], indent=1))
print("ERROR:", r["error"], r.get("debug"))
print("USAGE:", json.dumps(r["usage"]["totals"]), "elapsed", r.get("elapsed"))
