"""Head-to-head: ask the same model (gpt-6-luna) the same question the way a student would in
ChatGPT — (A) from memory, no tools; (B) with web search but no checking — and save the answers so
they can be audited against DealScout's checked results. Costs well under $0.10.
Usage: python scripts/baseline_compare.py"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pydantic import BaseModel
from dealscout.agents import client
from dealscout.ledger import CallRecord, call_cost

QUESTION = (f"Today is {time.strftime('%B %d, %Y')}. List the 5 most notable Aerospace & Defense M&A deals announced "
            "in the last 12 months worth at least $500 million. For each give buyer, target, deal value in $ millions, "
            "announcement date, the banks that advised each side, and a source URL.")


class D(BaseModel):
    buyer: str
    target: str
    value_usd_m: float | None
    announced: str
    advisors: list[str]
    source_url: str


class Ans(BaseModel):
    deals: list[D]


out = {}
for name, tools in [("A_memory_no_tools", None), ("B_web_search_no_checks", [{"type": "web_search"}])]:
    kw = dict(model="gpt-6-luna", input=QUESTION, text_format=Ans, reasoning={"effort": "low"})
    if tools:
        kw["tools"] = tools
    t0 = time.time()
    r = client().responses.parse(**kw)
    u = r.usage
    rec = CallRecord(agent=name, input_tokens=u.input_tokens,
                     cached_tokens=u.input_tokens_details.cached_tokens or 0,
                     cache_write_tokens=getattr(u.input_tokens_details, "cache_write_tokens", 0) or 0,
                     output_tokens=u.output_tokens,
                     web_searches=sum(o.type == "web_search_call" for o in r.output))
    out[name] = {"deals": [d.model_dump() for d in r.output_parsed.deals], "seconds": round(time.time() - t0, 1),
                 "tokens_in": rec.input_tokens, "tokens_out": rec.output_tokens, "searches": rec.web_searches,
                 "cost": round(call_cost(rec), 4)}
    print(name, json.dumps(out[name], indent=1))
out["question"] = QUESTION
(Path(__file__).resolve().parents[1] / "docs/evidence/baseline_compare.json").write_text(json.dumps(out, indent=1))
