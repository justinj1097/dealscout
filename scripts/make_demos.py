"""Run a few real searches and save them (with pitches for the top deals) as free demo examples.
Usage: python scripts/make_demos.py      (costs roughly $0.10 per example)"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dealscout import config
from dealscout.models import Criteria
from dealscout.pipeline import hunt, pitch

EXAMPLES = {
    "aerospace_defense": Criteria(industry="Aerospace & Defense", min_value_usd_m=500, months_back=12, num_deals=5),
    "technology_software": Criteria(industry="Technology / Software", min_value_usd_m=1000, months_back=12, num_deals=5),
    "healthcare_biotech": Criteria(industry="Healthcare & Biotech", min_value_usd_m=1000, months_back=12, num_deals=5),
}
names = sys.argv[1:] or list(EXAMPLES)
for name in names:
    h = hunt(EXAMPLES[name], session_id=f"demo-{name}", use_cache=False, progress=print)
    if h["error"]:
        print(name, "ERROR", h["error"]); continue
    for d in h["deals"][:2]:
        p = pitch(h["criteria"]["industry"], d)
        if p.get("pitch"):
            d["pitch"] = p
    (config.DEMO_DIR / f"{name}.json").write_text(json.dumps(h, indent=1))
    print(name, len(h["deals"]), "deals, $%.4f" % h["usage"]["totals"]["cost"])
