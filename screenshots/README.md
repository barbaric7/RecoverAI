# Screenshots

Captured from a live run (`gpt-4.1` via OpenRouter in hybrid mode, simulated Razorpay). 1280×900 @1.5×.

| # | File | What it shows |
|---|---|---|
| 01 | `01-overview.png` | Overview above the fold — stepper, 4 KPIs, outcomes, LLM-vs-policy callout |
| 02 | `02-overview-full.png` | Full overview incl. recovery-by-failure-reason and decisions table |
| 03 | `03-run-in-progress.png` | **Run recovery mid-flight** — stepper on *Act*, live counter, rows streaming in |
| 04 | `04-payment-P0042-retry-recovered.png` | Happy path: bank timeout → retry → ₹2,499 recovered, all 9 policy checks ✓ |
| 05 | `05-payment-P0003-payment-link.png` | Expired card → GPT-4.1 picks payment link (not retry) → recovered ₹8,999 |
| 06 | `06-payment-P0099-escalated.png` | ₹12,999 repeated failure → policy gate closes 2 gates → human review |
| 07 | `07-payment-P0117-retry-failed.png` | Correct retry, bank still declines → *Unresolved*, budget accounting shown |
| 08 | `08-payment-P0210-stale-event-blocked.png` | Payment already succeeded → policy blocks any action (no double charge) |
| 09 | `09-audit-P0210.png` | Audit timeline for the blocked case |
| 10 | `10-audit-P0042.png` | Audit timeline for the recovered case — 8 steps, action logged before execution |
| 11 | `11-audit-P0099-policy-filter.png` | Audit filtered to *Policy checks* chip |
| 12 | `12-audit-global-feed.png` | Cross-payment audit feed, latest events |
| 13 | `13-decisions-filter-escalated.png` | Decisions table filtered to *Escalated* |

Regenerate: start the backend, then run the Playwright snippet in `scripts/capture_screenshots.py`.
