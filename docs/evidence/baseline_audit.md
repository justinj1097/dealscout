# Head-to-head audit: same model, same question, three ways (Oct 25, 2026)

Question (identical for all): the 5 most notable Aerospace & Defense M&A deals announced in the last 12
months worth ≥ $500M, with buyer, target, value, date, advisor banks, and a source URL.
Raw answers: `baseline_compare.json`. DealScout's answer: `data/demo_runs/aerospace_defense.json`
(audited in `accuracy_audit.md`). Each claim was checked with independent web searches.

## A — gpt-6-luna from memory (like plain ChatGPT), $0.0008, 15 s
| Deal | Claimed date | Real announcement | In last 12 months? | Link |
|---|---|---|---|---|
| Safran → Collins actuation | 2025-07-21 | **July 21, 2023** (2025 was the closing) | ❌ | 403 |
| Leonardo → Iveco Defence Vehicles | 2025-03-18 | **July 30, 2025** | ❌ | 404 (invented) |
| Redwire → Edge Autonomy | 2025-01-13 | Jan 2025 | ❌ | 404 (invented) |
| TJC → L3Harris Commercial Aviation | 2025-01-30 | Jan 2025 | ❌ | 404 (invented) |
| Honeywell → CAES | 2024-06-20 | June 2024 | ❌ | 404 (invented) |
**0 / 5 inside the window, 2 / 5 wrong dates, 4 / 5 links do not exist, 0 banks.**

## B — gpt-6-luna + web search, no checks (like ChatGPT search / Perplexity), $0.0555, 42 s
| Deal | Value | Real & in window? | Banks claimed | Banks verified? |
|---|---|---|---|---|
| GE Aerospace → CPP | $11.75B | ✅ | "not disclosed" | ❌ missed: Evercore & PJT (GE), Morgan Stanley (CPP) are public |
| AAR → MRO Holdings (65%) | $4.0B EV | ✅ | Goldman, William Blair, Centerview / Solomon, RBC | ⚠ could not confirm in independent search |
| CACI → ARKA Group | $2.6B | ✅ | Wells Fargo / J.P. Morgan, Evercore | ✅ |
| TransDigm → Jet Parts Eng. & Victor Sierra | $2.2B | ✅ | not disclosed / Harris Williams | not checked |
| Howmet → CAM | $1.8B | ✅ | not disclosed | not checked |
**5 / 5 real and in window, values correct, 4 / 5 links work; banks: 1 confirmed, 1 unconfirmed, 3 missing.**
No ranking by user priority, no second-source check, no interview pitch, and nothing stops a wrong
number or link from reaching the user if the model slips.

## DealScout (same industry, saved example)
5 / 5 real and in window, 14 / 14 displayed values correct across all 15 audited deals; every deal
confirmed by a second, different website; banks found for 4 of 5 A&D deals; ranked by the user's
priority; 60-second pitch + likely questions on click. Cost ≈ $0.08 per search.

## Takeaway (honest)
Memory-only chat is unusable for recent deals (old deals, fake links). Web-search chat is already
good at deal facts; DealScout's advantages are the *guarantees* (code removes unsupported numbers and
links — live catches: SpaceX/xAI value mismatch, MDA C$/US$ mix-up), better advisor coverage,
ranking, and the interview pitch — at a similar cost per search.
