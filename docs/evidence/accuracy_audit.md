# Accuracy audit of DealScout's saved example deals (Oct 25, 2026)

Method: for each of the 15 deals shown in the three saved examples (`data/demo_runs/`), an independent
web search (not using DealScout) checked whether the deal exists, its parties, announcement date, and
headline value.

| # | Industry | Deal (buyer → target) | DealScout value | Independent sources say | Real? | Value correct? |
|---|---|---|---|---|---|---|
| 1 | A&D | Parker-Hannifin → CIRCOR Aerospace | $2.55B, 2026-05-21 | $2.55B cash, announced May 21, 2026 (MDM, Manufacturing.net) | ✅ | ✅ |
| 2 | A&D | GE Aerospace → Consolidated Precision Products | $11.75B, 2026-09-08 | $11.75B, Sept 8, 2026 (Bloomberg Law, AviationPros) | ✅ | ✅ |
| 3 | A&D | Joby Aviation → Resonant Sciences | $500M, 2026-08-11 | ~$500M, Aug 11, 2026 (Joby IR, CompositesWorld) | ✅ | ✅ |
| 4 | A&D | MDA Space → Blue Canyon Technologies | $620M, 2026-06-19 | US$620M (C$874M), June 19, 2026 (Via Satellite, GovConWire) | ✅ | ✅ |
| 5 | A&D | TransDigm → Prince & Izant | $1.066B, 2026-07-27, Closed | ~$1.066B, July 27, 2026; closed Sept 28, 2026 (SEC 8-Ks) | ✅ | ✅ |
| 6 | Healthcare | Vertex → Crinetics | $10B, 2026-07-06 | ~$10B equity value, early July 2026 (Financier Worldwide, BioXconomy) | ✅ | ✅ |
| 7 | Healthcare | Merck KGaA → Bio-Techne | $11.3B, 2026-06-25 | ~$11.3B EV, late June 2026 (American Pharmaceutical Review, DCAT) | ✅ | ✅ |
| 8 | Healthcare | Danaher → Masimo | $9.9B, 2026-02-17 | ~$9.9B EV, Feb 17, 2026 (Cleary Gottlieb, HPN) | ✅ | ✅ |
| 9 | Healthcare | Merck KGaA → Silence Therapeutics | $1.1B, 2026-10-19 | $1.1B EV / ~$1.3B equity, Oct 19, 2026 (Contract Pharma, Reuters via KSL) | ✅ | ✅ (EV; not labelled as EV) |
| 10 | Healthcare | Gilead → Arcellx | $7.8B, 2026-02-23 | ~$7.8B, Feb 2026 (Financier Worldwide, Nasdaq) | ✅ | ✅ |
| 11 | Tech | Proofpoint → Varonis | $6.3B, 2026-10-15 | ~$6.3B, Oct 15, 2026 (Bloomberg Government, iTWire) | ✅ | ✅ |
| 12 | Tech | Schneider Electric → PTC | $23.7B, 2026-10-05 | $23.7B EV / $22.6B equity (The Next Web, The Tech Capital) | ✅ | ✅ (EV; not labelled as EV) |
| 13 | Tech | Salesforce → Braze | $5.66B, 2026-10-20 | ~$5.66B EV, Oct 20, 2026 (The Star/Reuters, Dealroom) | ✅ | ✅ |
| 14 | Tech | IBM → Confluent | $11B, 2025-12-08 | $11B EV, Dec 2025 (AP via ABC News, Techzine) | ✅ | ✅ |
| 15 | Tech | GTCR & Elliott → CCC Intelligent Solutions | not shown (removed) | ~$6.1B EV, Oct 15, 2026 (CCC 8-K, Coverager) | ✅ | — value withheld: the Scout's quote held no dollar amount, so the Gatekeeper removed it (safe miss) |

**Result: 15 / 15 deals real (0 invented); 14 / 14 displayed values correct; 1 value correctly withheld.**

Findings to improve (reported in the report's limits section):
- Values mix enterprise value and equity value without saying which (deals 9 and 12).
- Advisor banks were not part of this audit. One entry (deal 15) lists "Morgan" as a buyer-side advisor,
  while coverage says Morgan Stanley ran CCC's sale process (seller side) — advisor data is less reliable
  than deal facts and should be double-checked before quoting.
- Status can go stale: a deal saved as "Pending" may close later (deal 5 was correctly "Closed").
