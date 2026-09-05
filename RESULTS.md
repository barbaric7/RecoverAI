# RecoverAI — Results

*Generated 2026-09-05 · 500 synthetic failed payments (seed 42) · agent brain: **deterministic fallback** (0 LLM / 500 fallback decisions)*

![results](docs/results.png)

> ⚠️ This run used the deterministic fallback (no `OPENAI_API_KEY`). The fallback encodes the same rules as the ground-truth labeller, so 100% accuracy is a pipeline sanity check, not a result. Re-run with a key for the real numbers.

## Headline

| Metric | Value |
|---|---|
| Revenue at risk | **₹2,064,700** |
| Revenue recovered | **₹540,308** (192 payments) |
| Recovery rate (recovered ÷ recoverable) | **56.8%** |
| Attempt success rate (recovered ÷ automated attempts) | 56.8% |
| Escalated to humans | 153 cases · ₹1,116,247 |
| Unresolved after one safe attempt | 146 |
| Marked unrecoverable | 9 |

## LLM proposes · policy engine controls

| | |
|---|---|
| Raw LLM decision accuracy | 100.0% |
| **Accuracy after policy gate** | **100.0%** |
| Actions blocked or downgraded by policy | 0 |

| Override | Count |
|---|---|
| — | 0 |

## By failure reason

| Failure reason | Cases | Recovered | Amount |
|---|---|---|---|
| BANK_TIMEOUT | 83 | 36 | ₹101,464 |
| INSUFFICIENT_FUNDS | 90 | 33 | ₹99,267 |
| BANK_ERROR | 49 | 25 | ₹60,675 |
| AUTH_FAILURE | 51 | 21 | ₹64,179 |
| CHECKOUT_ABANDONED | 42 | 14 | ₹38,886 |
| EXPIRED_CARD | 49 | 15 | ₹44,585 |
| PAYMENT_TIMEOUT | 45 | 21 | ₹61,679 |
| SUBSCRIPTION_FAILURE | 45 | 27 | ₹69,573 |
| REPEATED_FAILURE | 24 | 0 | ₹0 |
| CARD_BLOCKED | 14 | 0 | ₹0 |
| SUSPECTED_FRAUD | 8 | 0 | ₹0 |

## Final actions

`ESCALATE_TO_HUMAN` 153 · `RETRY_PAYMENT` 150 · `CREATE_PAYMENT_LINK` 126 · `WAIT_AND_RETRY` 62 · `MARK_UNRECOVERABLE` 9

## Definitions

- **Recovery rate** = recovered ÷ ground-truth-recoverable payments
- **Decision accuracy** = policy-approved final action == ground-truth action
- **Policy override** = final action ≠ LLM-recommended action
- Payment outcomes are drawn from a probability model in the synthetic dataset; decisions, policy enforcement and audit are real.
