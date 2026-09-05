# Demo media

Recorded from a live instance (GPT-4.1 via OpenRouter, hybrid mode; simulated Razorpay). 1280×800.

| Clip | Length | GIF | MP4 |
|---|---|---|---|
| `full` — end-to-end walkthrough (run → recovered → escalated → blocked → audit) | 65s | 3.8 MB | 1.2 MB |
| `run` — live batch run, decisions streaming | 40s | 3.0 MB | 0.9 MB |
| `recovered` — P0042 retry → ₹2,499 recovered → audit | 13s | 2.1 MB | 0.4 MB |
| `escalated` — P0099 policy override → human review → policy-checks filter | 12s | 1.9 MB | 0.4 MB |
| `stale` — P0210 stale event blocked · P0117 failed retry | 11s | 1.4 MB | 0.3 MB |

GIFs are tuned to stay under GitHub's inline-render limits; MP4s are the sharp versions for slides.
Regenerate all with `python scripts/record_media.py all`.
