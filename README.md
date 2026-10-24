# DealScout 🔎💼

**Find the M&A deals worth talking about in your industry — checked, ranked, and interview-ready.**

DealScout is an AI agent team for students recruiting for investment banking and for junior bankers.
You pick an industry (aerospace & defense, software, healthcare, …), a minimum deal size, and a time
window. Four AI agents search the live web and SEC filings, double-check every deal against a second
source, find the banks that advised, rank the deals, and turn any one of them into a 60-second
interview pitch with the follow-up questions you'll get.

Every number on screen comes from a source found during that search, and plain-Python safety checks
throw out deals with made-up links or numbers that don't match their own source.

> **Model:** `gpt-6-luna` through the course Portkey key (no other model is used).
> **Typical cost:** about $0.05–$0.10 per search, ≈ $0.001 per pitch; repeat searches are free for 24 h.

> **🌐 Try it online: https://dealscout-r8xm.onrender.com** (free hosting: the first visit may take ~30 s to wake up).
> **Or run it on your own computer** in about 5 minutes (below) — this is the fully supported path.

---

## Run it (about 5 minutes)

You need **Python 3.10 or newer** and the course **PORTKEY_API_KEY**.

```bash
# 1. Get the code
git clone <this-repo-url> dealscout
cd dealscout

# 2. Install (a virtual environment keeps things clean)
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Add the key — EITHER in this folder OR in the folder above it
cp .env.example .env                 # then put your key after PORTKEY_API_KEY=
#   (if a .env with PORTKEY_API_KEY already sits one folder up, skip this step)

# 4. Start the app
python app.py
```

Open **http://127.0.0.1:8050** in your browser.

- Port 8050 busy? Run `PORT=8051 python app.py` (Windows: `set PORT=8051` then `python app.py`).
- The terminal prints which `.env` file it found (never the key itself).

### Where DealScout looks for the key
1. `.env` in this repo's folder, then
2. `.env` in the folder **above** the repo (the teaching-staff layout: `submissions/.env`).

It reads `PORTKEY_API_KEY`. `OPENAI_API_KEY` is not used. See `.env.example`.

### No key? Use the saved examples
With no key the app opens in **demo mode**: "Find deals" is disabled, but the **"Open a saved
example"** menu shows real searches saved earlier (Aerospace & Defense, Technology / Software,
Healthcare & Biotech), including pitches for the top two deals. They cost nothing and need no internet.

---

## How to use it

1. Choose an **industry** (or "Other" and type one), an optional **focus** (e.g. "space"), a
   **minimum size**, a **time window**, and **what matters most** (best for interviews, biggest, most recent…).
2. Press **Find deals** (≈ 40 seconds). You get ranked deal cards: buyer → target, value, date, status,
   advisor banks, a "confirmed by 2nd source" badge, why it matters, and the interview angle.
3. Press **Build my 60-second pitch** on any deal for a spoken-style answer, key numbers, risks, and
   three likely follow-up questions with model answers.
4. The other tabs show **How the agents worked** (step-by-step trace), **Cost** (real token counts per
   agent from this run), and **Safety** (everything that was blocked or removed).
5. **Run the red-team safety check** throws 9 attacks at the app's defenses — offline, $0.

---

## How it works

```
Your form ─► Input guard (code) ─► Cache? ─► SCOUT (web search + SEC EDGAR)
          ─► Gatekeeper (code: fake links, number vs quote, criteria) ─► FACT-CHECKER (2nd source + banks)
          ─► score_deals (code) ─► ANALYST (why it matters) ─► results
                                     click a deal ─► PITCH COACH (+ deal-library comparables)
```

| Agent | Job | Tools |
|---|---|---|
| Scout | Finds candidate deals with an exact quote for each value | `web_search` (≤ 8 calls), `edgar_search` (SEC full-text search) |
| Fact-Checker | Confirms each deal with a *different* source; finds advisor banks | `web_search` (≤ 6 calls) |
| Analyst | Explains why each ranked deal matters and how to use it in an interview | `score_deals` (code) |
| Pitch Coach | Writes the 60-second pitch and likely interview Q&A | `get_comparables` (local deal library) |

Plain Python (not AI) runs the hand-offs and all safety checks, so a prompt injection cannot talk its way past them.

### Safety and spending limits (all in `dealscout/config.py`)
- Web pages are treated as untrusted data: hidden text, HTML comments, and zero-width tricks are
  removed; fields carrying injected orders are dropped; later agents only see cleaned, structured fields.
- A deal is dropped if its link never appeared in a real search result; a number is removed if the
  agent's own quoted sentence doesn't support it (currency-aware).
- Caps: Scout ≤ 8 searches, Fact-Checker ≤ 6, ≤ 4 tool rounds per agent, $0.25 per run,
  $5.00 per day for the whole app (`DEALSCOUT_DAILY_BUDGET`), 6 live searches per visitor (IP address)
  per 10 minutes, and 40 live searches per hour for the whole app (`DEALSCOUT_RUNS_PER_HOUR`).
- API keys are never sent to the model and are redacted from anything shown on screen.

---

## Tests (offline, free)

```bash
python -m pytest -q
```
Checks every red-team attack is stopped, the number/currency checker, the cost math, the token cap,
and that the `.env` is found **one folder up**.

## Other commands

```bash
python run_cli.py "Aerospace & Defense" --min 500 --months 12   # one search in the terminal
python scripts/make_demos.py                                   # re-create the saved examples (~$0.25)
```

## Online version (Render)
`render.yaml` deploys the same code to Render's free tier: render.com → **New → Blueprint** → choose this
repo → paste `PORTKEY_API_KEY` when asked → **Apply**. It runs with gunicorn, a $3/day budget, and 30 live
searches per hour. Free instances sleep after ~15 minutes idle, so the first visit takes ~30 s.

## Data
DealScout does not ship a large dataset: deals are found live. The small files in `data/` are
- `data/demo_runs/*.json` — saved real searches used by demo mode (the "test dataset").
- `data/deal_library.json` — verified deals collected from past searches; the Pitch Coach uses it for comparables.

To switch: **live mode** = key present + "Find deals"; **saved mode** = pick an example (works with or without a key).

## Project layout
```
app.py                 Dash web app (black & pink UI)
dealscout/agents.py    the four agents + shared run_agent loop (budget checks, ledger, tool loop cap)
dealscout/pipeline.py  orchestrator, Gatekeeper, cache, pitch generation
dealscout/safety.py    injection detection, page cleaning, grounding checks, redaction
dealscout/ledger.py    token ledger, cost math, per-run / per-day caps
dealscout/tools.py     SEC EDGAR search, scoring formula, deal library / comparables
dealscout/redteam.py   the 9 offline attacks behind the red-team button and tests
dealscout/prompts/     each agent's instructions
tests/                 pytest suite
docs/                  report.html, slides.html, screenshots
```

*Educational project for MGT 409 AI Foundations. Deal information comes from public sources and may
be incomplete; verify before using it in a real interview or on the job.*
