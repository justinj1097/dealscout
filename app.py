"""DealScout – find the M&A deals worth talking about in your industry, checked and interview-ready.

Run:  python app.py   then open http://127.0.0.1:8050
"""

from __future__ import annotations

import json
import os
import uuid

from dash import ALL, Dash, Input, Output, State, ctx, dcc, html, no_update

from dealscout import config, pipeline, redteam
from dealscout.models import Criteria

INDUSTRIES = ["Aerospace & Defense", "Technology / Software", "Semiconductors", "Healthcare & Biotech",
              "Medical Devices", "Financial Services & Fintech", "Energy (Oil & Gas)", "Power & Utilities",
              "Industrials", "Consumer & Retail", "Media & Telecom", "Real Estate",
              "Transportation & Logistics", "Chemicals & Materials", "Other (type below)"]
SIZES = [("$100M+", 100), ("$250M+", 250), ("$500M+", 500), ("$1B+", 1000), ("$5B+", 5000), ("$10B+", 10000)]
WINDOWS = [("3 months", 3), ("6 months", 6), ("12 months", 12), ("24 months", 24)]
PRIORITIES = ["Best for interviews", "Biggest deals", "Most recent", "Most talked-about"]
DEMOS = sorted(p.stem for p in config.DEMO_DIR.glob("*.json")) if config.DEMO_DIR.is_dir() else []

app = Dash(__name__, title="DealScout", suppress_callback_exceptions=True)
server = app.server


def field(label, child):
    return html.Div([html.Label(label), child], className="field")


def search_panel():
    has_key = bool(config.portkey_key())
    return html.Div(className="panel", children=[
        html.H3("What are you looking for?"),
        html.P("Pick your industry and what matters to you. DealScout's agents search the web and SEC filings, "
               "double-check every deal, and rank the ones worth talking about.", className="hint"),
        field("Industry", dcc.Dropdown(INDUSTRIES, "Aerospace & Defense", id="industry", clearable=False)),
        html.Div(id="other-wrap", style={"display": "none"},
                 children=field("Your industry", dcc.Input(id="industry-other", type="text", placeholder="e.g. Cybersecurity"))),
        field("Focus (optional)", dcc.Input(id="focus", type="text", placeholder="e.g. space, defense electronics")),
        field("Minimum deal size", dcc.Dropdown([{"label": a, "value": b} for a, b in SIZES], 500, id="min", clearable=False)),
        field("Announced in the last", dcc.Dropdown([{"label": a, "value": b} for a, b in WINDOWS], 12, id="months", clearable=False)),
        field("Region", dcc.Dropdown(["Global", "North America", "Europe", "Asia-Pacific"], "Global", id="region", clearable=False)),
        field("What matters most", dcc.RadioItems(PRIORITIES, "Best for interviews", id="priority", className="radio-row")),
        field("How many deals", dcc.Dropdown([3, 4, 5, 6, 8], 5, id="num", clearable=False)),
        field("Anything else? (optional)", dcc.Textarea(id="note", maxLength=400,
              placeholder="e.g. I'm interviewing at a defense-focused boutique next week")),
        html.Button("Find deals", id="go", className="btn", disabled=not has_key),
        html.P("Takes about 40 seconds and costs about 9¢. Repeat searches are free for 24 h." if has_key else
               "No API key found, so live search is off. Try a saved example below.", className="hint",
               style={"marginTop": "10px", "textAlign": "center"}),
        html.Div(className="divider"),
        html.H3("Or open a saved example", style={"fontSize": "15px"}),
        html.P("Real searches saved earlier. Free and instant.", className="hint"),
        dcc.Dropdown([{"label": d.replace("_", " ").title(), "value": d} for d in DEMOS], None, id="demo",
                     placeholder="Choose an example…"),
        html.Div(className="divider"),
        html.Button("Run the red-team safety check", id="redteam-btn", className="btn ghost"),
        html.P("Throws 9 attacks at the app's defenses. Offline, $0.", className="hint", style={"marginTop": "8px", "textAlign": "center"}),
    ])


def empty_state():
    return html.Div(className="empty", children=[
        html.Div("Find the deals worth talking about.", className="big"),
        html.Div("Pick an industry on the left and press Find deals."),
        html.Div(className="steps", children=[
            html.Div([html.B("1 · Scout"), "searches the web + SEC filings for real deals"], className="step"),
            html.Div([html.B("2 · Gatekeeper"), "drops fake links and numbers that don't match their source"], className="step"),
            html.Div([html.B("3 · Fact-Checker"), "confirms each deal with a second source and finds the banks"], className="step"),
            html.Div([html.B("4 · Analyst"), "ranks them and says why each one matters"], className="step"),
            html.Div([html.B("5 · Pitch Coach"), "turns one deal into a 60-second interview answer"], className="step"),
        ])])


app.layout = html.Div([
    dcc.Store(id="session", storage_type="session"),
    dcc.Store(id="hunt"),
    dcc.Store(id="pitch-store"),
    html.Div(className="topbar", children=[
        html.Div([html.Div(["Deal", html.Span("Scout")], className="logo"),
                  html.Div("Find the deals worth talking about in your industry — checked, ranked, and interview-ready.",
                           className="tagline")]),
        html.Span("● live: gpt-6-luna" if config.portkey_key() else "● demo mode (no API key)",
                  className="pill live" if config.portkey_key() else "pill"),
    ]),
    html.Div(className="wrap", children=[
        search_panel(),
        html.Div([
            dcc.Tabs(id="tabs", value="deals", className="tab-bar", children=[
                dcc.Tab(label="Deals", value="deals", className="tab", selected_className="tab--selected"),
                dcc.Tab(label="How the agents worked", value="trace", className="tab", selected_className="tab--selected"),
                dcc.Tab(label="Cost", value="cost", className="tab", selected_className="tab--selected"),
                dcc.Tab(label="Safety", value="safety", className="tab", selected_className="tab--selected"),
            ]),
            html.Div(id="status"),
            dcc.Loading(type="circle", color="#ff4fa3", children=html.Div(id="main", children=empty_state())),
        ]),
    ]),
    html.Div("DealScout · facts come only from sources found in each search · always confirm numbers before you quote them",
             className="footer"),
])


# ------------------------------------------------------------------ helpers
def money(v):
    if v is None:
        return "Undisclosed"
    return f"${v / 1000:,.2f}B" if v >= 1000 else f"${v:,.0f}M"


VERDICT_CLASS = {"confirmed": "ok", "partly confirmed": "mid", "could not confirm": "mid", "conflict": "bad"}
VERDICT_TEXT = {"confirmed": "✓ Confirmed by 2nd source", "partly confirmed": "◐ Partly confirmed",
                "could not confirm": "? Not independently confirmed", "conflict": "✗ Sources conflict"}


def deal_card(i, d):
    banks = []
    if d.get("buyer_advisors"):
        banks += [html.Span("Buyer:", className="chip side")] + [html.Span(b, className="chip") for b in d["buyer_advisors"]]
    if d.get("seller_advisors"):
        banks += [html.Span("Seller:", className="chip side")] + [html.Span(b, className="chip") for b in d["seller_advisors"]]
    if not banks:
        banks = [html.Span("Advisors not found in sources", className="chip side")]
    mult = [f"{d['ev_ebitda']:.1f}x EV/EBITDA" if d.get("ev_ebitda") else None,
            f"{d['ev_revenue']:.1f}x EV/Revenue" if d.get("ev_revenue") else None]
    links = [html.A("Source", href=d["source_url"], target="_blank")]
    if d.get("second_source"):
        links.append(html.A("2nd source", href=d["second_source"], target="_blank"))
    return html.Div(className="card", children=[
        html.Div(className="card-top", children=[
            html.Div([
                html.Div(f"#{i + 1}  ·  SCORE {d.get('score', 0):.0f}", className="rank"),
                html.Div([d["acquirer"], html.Span("→", className="arrow"), d["target"]], className="deal-title"),
                html.Div(className="meta", children=[
                    html.Span(d.get("deal_type", "")), html.Span(f"Announced {d.get('announced_date', '?')}"),
                    html.Span(d.get("status", "")), *[html.Span(m) for m in mult if m],
                    html.Span(VERDICT_TEXT.get(d.get("verdict"), "?"), className=f"badge {VERDICT_CLASS.get(d.get('verdict'), 'mid')}"),
                ]),
            ]),
            html.Div([money(d.get("value_usd_m")), html.Small("deal value" if d.get("value_usd_m") else d.get("value_note", ""))],
                     className="value"),
        ]),
        html.Div(banks, className="chips"),
        html.Div([html.B("Why it matters: "), d.get("why_it_matters") or d.get("strategic_rationale", "")], className="why"),
        html.Div([html.B("Interview angle: "), d.get("interview_angle", "")], className="why") if d.get("interview_angle") else None,
        html.Div(className="card-foot", children=[
            html.Div([*links, html.Span(f"· {d.get('check_note', '')}")], className="sources"),
            html.Button("Build my 60-second pitch →", id={"type": "pitch-btn", "index": i}, className="btn small"),
        ]),
    ])


def deals_view(h, p=None):
    if h.get("error") and not h.get("deals"):
        return html.Div(h["error"], className="notice err")
    t = h.get("usage", {}).get("totals", {})
    c = h.get("criteria", {})
    head = [
        html.Div(className="summary", children=[
            html.Div([html.Div(len(h["deals"]), className="v"), html.Div("deals found", className="l")], className="stat"),
            html.Div([html.Div(sum(d.get("verdict") == "confirmed" for d in h["deals"]), className="v"),
                      html.Div("confirmed by a 2nd source", className="l")], className="stat"),
            html.Div([html.Div(len(h.get("rejected", [])) + len(h.get("safety", [])), className="v"),
                      html.Div("problems caught", className="l")], className="stat"),
            html.Div([html.Div("$0.00 (saved)" if h.get("cached") else f"${t.get('cost', 0):.3f}", className="v"),
                      html.Div(f"cost · {h.get('elapsed', 0)} s" if not h.get("cached") else "reused saved search", className="l")],
                     className="stat"),
        ]),
    ]
    if h.get("demo"):
        head.append(html.Div(f"Saved example: {c.get('industry')} · ≥ ${c.get('min_value_usd_m', 0):,.0f}M · "
                             f"last {c.get('months_back')} months · saved {h.get('saved_time', '')}. "
                             "Numbers were checked when it was saved.", className="notice"))
    if h.get("theme"):
        head.append(html.Div([html.B("The big picture: "), h["theme"]], className="theme"))
    cards = []
    for i, d in enumerate(h["deals"]):
        cards.append(deal_card(i, d))
        if p and p.get("deal") == i:
            cards.append(pitch_block(p, h))
    return html.Div(head + cards)


FLOW = ["Input guard", "Scout", "Gatekeeper", "Fact-Checker", "score_deals", "Analyst", "Pitch Coach"]
AI = {"Scout", "Fact-Checker", "Analyst", "Pitch Coach"}


def trace_view(h):
    flow = []
    for i, f in enumerate(FLOW):
        flow.append(html.Span(f, className="ai" if f in AI else ""))
        if i < len(FLOW) - 1:
            flow.append(html.I("→"))
    blocks = [html.Div(flow, className="flow"),
              html.P("Pink = AI agent (gpt-6-luna). Grey = plain code the AI can't talk its way past.", className="hint")]
    for t in h.get("trace", []):
        blocks.append(html.Div([html.H4(t["agent"]), *[html.Div(s, className="s") for s in t["steps"]]], className="trace-agent"))
    return html.Div(blocks)


def cost_table(rows, total):
    head = html.Tr([html.Th(x) for x in ("Agent", "Input", "Cached in", "Output", "Reasoning", "Web searches", "Seconds", "Cost")])
    def r(x, cls=None):
        return html.Tr([html.Td(x["agent"]), html.Td(f"{x['input_tokens']:,}"), html.Td(f"{x['cached_tokens']:,}"),
                        html.Td(f"{x['output_tokens']:,}"), html.Td(f"{x['reasoning_tokens']:,}"), html.Td(x["web_searches"]),
                        html.Td(f"{x['seconds']:.0f}"), html.Td(f"${x['cost']:.4f}")], className=cls)
    return html.Table([head] + [r(x) for x in rows] + [r(total | {"agent": "Total"}, "total")], className="t")


def cost_view(h, pitch_usage):
    if h.get("cached"):
        body = [html.Div("This search reused a saved result from the last 24 hours: 0 tokens, $0.00. "
                         "Saved searches are the biggest cost saver in DealScout.", className="notice")]
    else:
        u = h.get("usage", {})
        body = [html.P("Measured from this run's API responses (usage field). Prices: gpt-6-luna $0.10 / 1M input, "
                       "$0.01 / 1M cached input, $0.125 / 1M cache write, $0.50 / 1M output; web search $0.01 per call.", className="hint"),
                cost_table(u.get("by_agent", []), u.get("totals", {}))]
    if pitch_usage:
        body += [html.H4("Pitch Coach (last pitch)", style={"marginTop": "20px"}),
                 cost_table(pitch_usage.get("by_agent", []) or [], pitch_usage.get("totals", {}) | {"agent": "Total"})
                 if pitch_usage.get("by_agent") else html.Div("Reused a saved pitch: $0.00", className="notice")]
    limits = (f"Limits: Scout ≤ {config.MAX_SEARCHES_SCOUT} searches, Fact-Checker ≤ {config.MAX_SEARCHES_CHECKER}, "
              f"≤ {config.MAX_TOOL_ROUNDS} tool rounds per agent, ${config.RUN_COST_CAP:.2f} per run, "
              f"${config.DAILY_COST_CAP:.2f} per day for the whole app, {config.RUNS_PER_10_MIN} live searches per 10 min per user.")
    return html.Div(body + [html.P(limits, className="hint", style={"marginTop": "16px"})])


def safety_view(h, rt):
    blocks = []
    if rt:
        passed = sum(r["stopped"] for r in rt)
        blocks += [html.H3(f"Red-team check: {passed} of {len(rt)} attacks stopped", style={"marginTop": 0})]
        blocks += [html.Div([html.B(("✓ STOPPED  " if r["stopped"] else "✗ GOT THROUGH  ") + r["attack"]), html.Br(),
                             html.Span(r["evidence"])], className="event ok" if r["stopped"] else "event") for r in rt]
        blocks.append(html.Div(className="divider"))
    if h:
        ev = h.get("safety", [])
        rej = h.get("rejected", [])
        blocks.append(html.H3("This search", style={"marginTop": 0}))
        if not ev and not rej:
            blocks.append(html.Div("No problems caught in this search.", className="notice"))
        blocks += [html.Div([html.B(e["kind"].upper() + " · "), f"{e['where']}: {e['detail']}"], className="event") for e in ev]
        blocks += [html.Div([html.B("DEAL REJECTED · "), f"{r['deal']}: {r['reason']}"], className="event") for r in rej]
    if not blocks:
        blocks = [html.Div("Run a search or the red-team check to see the safety log.", className="notice")]
    return html.Div(blocks)


# ------------------------------------------------------------------ callbacks
@app.callback(Output("other-wrap", "style"), Input("industry", "value"))
def toggle_other(v):
    return {"display": "block"} if v and v.startswith("Other") else {"display": "none"}


@app.callback(Output("session", "data"), Input("session", "data"))
def make_session(s):
    return s or uuid.uuid4().hex


RUNNING_NOTE = html.Div(className="working", children=[
    html.Div(className="dot-pulse"),
    html.Div([html.B("Your agents are working (about 40 seconds)"), html.Br(),
              "Scout is searching the web and SEC filings → Gatekeeper checks links and numbers → "
              "Fact-Checker confirms each deal with a second source → Analyst ranks them."])])


@app.callback(Output("hunt", "data"), Output("tabs", "value"), Output("pitch-store", "data"),
              Input("go", "n_clicks"), Input("demo", "value"), Input("redteam-btn", "n_clicks"),
              State("industry", "value"), State("industry-other", "value"), State("focus", "value"), State("min", "value"),
              State("months", "value"), State("region", "value"), State("priority", "value"), State("num", "value"),
              State("note", "value"), State("session", "data"), State("hunt", "data"), prevent_initial_call=True,
              running=[(Output("go", "disabled"), True, not config.portkey_key()),
                       (Output("go", "children"), "Agents at work… about 40 seconds", "Find deals"),
                       (Output("status", "children"), RUNNING_NOTE, None)])
def run(go, demo, rt, industry, other, focus, mn, months, region, priority, num, note, session, current):
    trig = ctx.triggered_id
    if trig == "redteam-btn":
        res = [vars(r) for r in redteam.run_all()]
        return (current or {}) | {"redteam": res}, "safety", no_update
    if trig == "demo":
        if not demo:
            return no_update, no_update, no_update
        h = json.loads((config.DEMO_DIR / f"{demo}.json").read_text())
        h["demo"] = True
        return h, "deals", None
    ind = (other or "").strip() if industry.startswith("Other") else industry
    if not ind:
        return {"error": "Please type your industry.", "deals": []}, "deals", None
    c = Criteria(industry=ind[:60], focus=(focus or "")[:80], min_value_usd_m=mn, months_back=months, region=region,
                 priority=priority, num_deals=num, note=note or "")
    return pipeline.hunt(c, session_id=session or "anon"), "deals", None


@app.callback(Output("pitch-store", "data", allow_duplicate=True), Input({"type": "pitch-btn", "index": ALL}, "n_clicks"),
              State("hunt", "data"), State("session", "data"), prevent_initial_call=True)
def make_pitch(clicks, h, session):
    if not ctx.triggered_id or not any(clicks) or not h:
        return no_update
    i = ctx.triggered_id["index"]
    d = h["deals"][i]
    if h.get("demo") and d.get("pitch"):
        return d["pitch"] | {"deal": i}
    if not config.portkey_key():
        return {"error": "Pitches for saved examples need an API key unless one was saved with the example.", "deal": i}
    return pipeline.pitch(h["criteria"]["industry"], d, session or "anon") | {"deal": i}


@app.callback(Output("main", "children"), Input("tabs", "value"), Input("hunt", "data"), Input("pitch-store", "data"))
def render(tab, h, p):
    rt = (h or {}).get("redteam")
    if tab == "safety":
        return safety_view(h if h and "criteria" in h else None, rt)
    if not h or "deals" not in h:
        return empty_state()
    if tab == "trace":
        view = trace_view(h)
        if p and p.get("steps"):
            view.children.append(html.Div([html.H4("Pitch Coach"), *[html.Div(s, className="s") for s in p["steps"]]],
                                          className="trace-agent"))
        return view
    if tab == "cost":
        return cost_view(h, (p or {}).get("usage"))
    return deals_view(h, p)


def pitch_block(p, h):
    if p.get("error") or not p.get("pitch"):
        return html.Div(p.get("error", "No pitch."), className="notice err", id="pitch")
    x, d = p["pitch"], h["deals"][p["deal"]]
    return html.Div(className="pitch", id="pitch", children=[
        html.Div("YOUR 60-SECOND PITCH" + ("  ·  saved, $0.00" if p.get("cached") else
                                           f"  ·  ${p.get('usage', {}).get('totals', {}).get('cost', 0):.4f}"), className="rank"),
        html.H2(x["headline"]),
        html.Div(x["sixty_second_pitch"], className="say"),
        html.H4("Key numbers"),
        html.Div([html.Div([html.B(k["value"]), html.Span(k["label"])]) for k in x["key_numbers"]], className="kn"),
        html.Div(className="pitch-grid", children=[
            html.Div([html.H4("Why it makes sense"), html.Ul([html.Li(b) for b in x["why_it_makes_sense"]])]),
            html.Div([html.H4("Risks to mention"), html.Ul([html.Li(b) for b in x["risks"]])]),
        ]),
        html.H4("Questions they'll ask you next"),
        *[html.Div([html.B(q["question"]), html.Br(), q["answer"]], className="qa") for q in x["interview_questions"]],
        html.Div(["Sources: ", html.A("primary", href=d["source_url"], target="_blank"),
                  *([" · ", html.A("second source", href=d["second_source"], target="_blank")] if d.get("second_source") else [])],
                 className="sources", style={"marginTop": "10px"}),
    ])


app.clientside_callback(
    """function(clicks) {
        const t = window.dash_clientside.callback_context.triggered_id;
        return clicks.map((c, i) => (t && t.index === i && c) ? "Writing your pitch… about 20 seconds" : window.dash_clientside.no_update);
    }""",
    Output({"type": "pitch-btn", "index": ALL}, "children"),
    Input({"type": "pitch-btn", "index": ALL}, "n_clicks"), prevent_initial_call=True)

app.clientside_callback(
    """function(p) {
        if (p) { setTimeout(() => { const el = document.getElementById("pitch");
                 if (el) el.scrollIntoView({behavior: "smooth", block: "start"}); }, 350); }
        return window.dash_clientside.no_update;
    }""",
    Output("status", "title"), Input("pitch-store", "data"), prevent_initial_call=True)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8050"))
    print(f"DealScout running at http://127.0.0.1:{port}  (key file: {config.ENV_FILE or 'none found'})")
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=port, debug=False)
