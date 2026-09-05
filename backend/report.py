"""Generate RESULTS.md + results.png from an evaluate.py JSON dump.

  python evaluate.py --json ../data/eval.json
  python report.py ../data/eval.json            # -> ../RESULTS.md, ../docs/results.png
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def inr(n: float) -> str:
    return f"₹{n:,.0f}"


def chart(m: dict, out: str) -> None:
    os.makedirs(os.path.dirname(out), exist_ok=True)
    bg, fg, muted = "#0b0f17", "#e5e9f0", "#8b95a7"
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), facecolor=bg)
    for ax in axes:
        ax.set_facecolor(bg)
        for s in ax.spines.values():
            s.set_color("#1f2a3d")
        ax.tick_params(colors=muted, labelsize=9)

    # 1. funnel
    ax = axes[0]
    labels = ["Processed", "Recoverable", "Recovered", "Escalated", "Unresolved", "Unrecoverable"]
    vals = [m["processed"], m["recoverable_count"], m["recovered_count"], m["escalated_count"], m["unresolved_count"], m["unrecoverable_count"]]
    cols = ["#60a5fa", "#a78bfa", "#22c55e", "#f59e0b", "#64748b", "#ef4444"]
    ax.barh(labels[::-1], vals[::-1], color=cols[::-1])
    for i, v in enumerate(vals[::-1]):
        ax.text(v + 4, i, str(v), va="center", color=fg, fontsize=9)
    ax.set_title("Outcomes (500 payments)", color=fg, fontsize=11, loc="left")
    ax.set_xlim(0, max(vals) * 1.18)

    # 2. money
    ax = axes[1]
    money = [m["at_risk_amount"], m["recovered_amount"], m["escalated_amount"]]
    ax.bar(["At risk", "Recovered", "Escalated\n(human review)"], money, color=["#334155", "#22c55e", "#f59e0b"], width=0.6)
    for i, v in enumerate(money):
        ax.text(i, v, inr(v), ha="center", va="bottom", color=fg, fontsize=9)
    ax.set_title("Revenue (INR)", color=fg, fontsize=11, loc="left")
    ax.set_ylim(0, max(money) * 1.15)
    ax.yaxis.set_visible(False)

    # 3. LLM vs policy
    ax = axes[2]
    acc = [m["llm_raw_accuracy"], m["decision_accuracy"]]
    ax.bar(["LLM raw", "After policy gate"], acc, color=["#8b5cf6", "#22c55e"], width=0.5)
    for i, v in enumerate(acc):
        ax.text(i, v + 1, f"{v:.1f}%", ha="center", color=fg, fontsize=10, fontweight="bold")
    ax.set_ylim(0, 110)
    ax.set_title(f"Decision accuracy · {m['policy_overrides']} actions blocked/downgraded", color=fg, fontsize=11, loc="left")
    ax.yaxis.set_visible(False)

    fig.suptitle("RecoverAI — evaluation", color=fg, fontsize=13, x=0.01, ha="left", fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(out, dpi=150, facecolor=bg)


def markdown(m: dict, chart_rel: str) -> str:
    mode = "LLM" if m["llm_decisions"] else "deterministic fallback"
    rows = "\n".join(
        f"| {r} | {v['count']} | {v['recovered']} | {inr(v['amount_recovered'])} |"
        for r, v in sorted(m["by_failure_reason"].items(), key=lambda kv: -kv[1]["at_risk"])
    )
    overrides = "\n".join(f"| `{k}` | {v} |" for k, v in sorted(m["policy_override_breakdown"].items(), key=lambda kv: -kv[1])) or "| — | 0 |"
    caveat = (
        ""
        if m["llm_decisions"]
        else "\n> ⚠️ This run used the deterministic fallback (no `OPENAI_API_KEY`). The fallback encodes the same rules as the "
        "ground-truth labeller, so 100% accuracy is a pipeline sanity check, not a result. Re-run with a key for the real numbers.\n"
    )
    return f"""# RecoverAI — Results

*Generated {date.today().isoformat()} · 500 synthetic failed payments (seed 42) · agent brain: **{mode}** ({m['llm_decisions']} LLM / {m['fallback_decisions']} fallback decisions)*

![results]({chart_rel})
{caveat}
## Headline

| Metric | Value |
|---|---|
| Revenue at risk | **{inr(m['at_risk_amount'])}** |
| Revenue recovered | **{inr(m['recovered_amount'])}** ({m['recovered_count']} payments) |
| Recovery rate (recovered ÷ recoverable) | **{m['recovery_rate']:.1f}%** |
| Attempt success rate (recovered ÷ automated attempts) | {m['attempt_success_rate']:.1f}% |
| Escalated to humans | {m['escalated_count']} cases · {inr(m['escalated_amount'])} |
| Unresolved after one safe attempt | {m['unresolved_count']} |
| Marked unrecoverable | {m['unrecoverable_count']} |

## LLM proposes · policy engine controls

| | |
|---|---|
| Raw LLM decision accuracy | {m['llm_raw_accuracy']:.1f}% |
| **Accuracy after policy gate** | **{m['decision_accuracy']:.1f}%** |
| Actions blocked or downgraded by policy | {m['policy_overrides']} |

| Override | Count |
|---|---|
{overrides}

## By failure reason

| Failure reason | Cases | Recovered | Amount |
|---|---|---|---|
{rows}

## Final actions

{" · ".join(f"`{k}` {v}" for k, v in sorted(m['final_action_counts'].items(), key=lambda kv: -kv[1]))}

## Definitions

- **Recovery rate** = recovered ÷ ground-truth-recoverable payments
- **Decision accuracy** = policy-approved final action == ground-truth action
- **Policy override** = final action ≠ LLM-recommended action
- Payment outcomes are drawn from a probability model in the synthetic dataset; decisions, policy enforcement and audit are real.
"""


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "eval.json")
    with open(src) as f:
        m = json.load(f)
    png = os.path.join(ROOT, "docs", "results.png")
    chart(m, png)
    md = os.path.join(ROOT, "RESULTS.md")
    with open(md, "w") as f:
        f.write(markdown(m, "docs/results.png"))
    print(f"wrote {md} and {png}")
