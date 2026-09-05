import { useEffect, useState } from 'react'
import { api, inrFull, title } from './api'
import { Badge, act } from './ui'

const CHECK_LABEL = {
  no_prior_success: ['Not already paid', 'Already paid — no action allowed'],
  amount_limit: ['Below ₹10,000 limit', 'Above ₹10,000 auto limit'],
  confidence_threshold: ['Confidence ≥ 0.55', 'Confidence below 0.55 threshold'],
  not_high_risk: ['Not suspected fraud', 'Fraud / blocked-card signal'],
  recovery_budget: ['Recovery budget remaining', 'Recovery budget exhausted'],
  retry_limit: ['Within retry limit', 'Retry limit exceeded'],
  retryable_failure_type: ['Failure type is retryable', 'Failure type not retryable'],
  customer_eligible: ['Customer history eligible', 'Weak customer history'],
  freshness: ['Within 7-day window', 'Failure older than 7 days'],
  not_premature_giveup: ['Write-off justified', 'Write-off looks premature'],
  escalation_always_allowed: ['Escalation always permitted', ''],
}
const ago = (d) => (d < 1 ? `${Math.max(1, Math.round(d * 24))}h ago` : `${Math.round(d)} day${Math.round(d) === 1 ? '' : 's'} ago`)

export default function PaymentDetails({ paymentId, onBack, onAudit, onChanged, setStep }) {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const load = () => api.payment(paymentId).then(setData).catch((e) => setErr(String(e)))
  useEffect(() => { setData(null); load() }, [paymentId])

  const c = data?.case
  useEffect(() => {
    if (!data) return
    if (!c) setStep({ active: 0 })
    else setStep({ active: 5, blocked: !c.policy.allowed, policyIdx: 2 })
  }, [data])

  const run = async () => {
    setBusy(true)
    try { await api.runOne(paymentId); await load(); onChanged?.() } catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }

  if (err) return <div className="banner-error">{err}</div>
  if (!data) return <div className="empty">Loading…</div>

  const p = data.payment
  const d = c?.decision, pol = c?.policy, ex = c?.execution
  const status = c?.status || 'PENDING'
  const blocked = !!pol && !pol.allowed
  const attemptsTxt = `${p.attempt_count + (ex && ['RETRY_PAYMENT', 'WAIT_AND_RETRY'].includes(ex.action) ? 1 : 0)} of 2 allowed`

  const resultTone = status === 'RECOVERED' ? '' : status === 'UNRESOLVED' ? 'bad' : status === 'ESCALATED' ? 'warn' : 'neutral'
  const resultText = {
    RECOVERED: inrFull(ex?.amount_recovered) + ' recovered',
    ESCALATED: 'Escalated',
    UNRESOLVED: 'Not recovered',
    UNRECOVERABLE: 'No action',
  }[status] || '—'

  return (
    <>
      <button className="back" onClick={onBack}>← Overview</button>
      <div className="detail-head">
        <div>
          <div className="detail-title mono">{p.payment_id} <Badge status={status} /></div>
          <div className="detail-sub">
            Failed <span className="mono">{ago(p.days_since_failure)}</span> · Customer history <span className="mono">{Math.round(p.customer_success_rate * 100)}%</span> ({p.previous_payments} payments) · Attempt <span className="mono">{attemptsTxt}</span>
            {p.subscription_status !== 'NONE' && <> · Subscription <span className="mono">{p.subscription_status.toLowerCase()}</span></>}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
          <div>
            <div className="amount-label">Amount</div>
            <div className="amount-big">{inrFull(p.amount)}</div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn-ghost" onClick={() => onAudit(p.payment_id)} disabled={!c}>Audit trail</button>
            <button className="btn" onClick={run} disabled={busy}>{busy ? 'Running…' : c ? 'Re-run agent' : 'Run agent'}</button>
          </div>
        </div>
      </div>

      <div className="rail">
        <div className="rail-items">

          <div className="rail-item">
            <div className="rail-node done">✓</div>
            <div className="rail-card">
              <div className="rail-kicker">Failure</div>
              <div className="rail-body">
                {p.failure_message}. <strong>{title(p.failure_reason)}</strong>
                {p.attempt_count > 0 && <> after {p.attempt_count} prior attempt{p.attempt_count > 1 ? 's' : ''}</>}
                {p.previous_recovery_attempts > 0 && <>, {p.previous_recovery_attempts} previous recovery attempt{p.previous_recovery_attempts > 1 ? 's' : ''}</>}.
                {p.payment_already_succeeded && <> <strong style={{ color: 'var(--danger)' }}>Stale event — payment already succeeded.</strong></>}
              </div>
              <div className="rail-meta">
                <span>Customer <span className="mono">{p.customer_id}</span></span>
                <span>Success rate <span className="mono">{Math.round(p.customer_success_rate * 100)}%</span></span>
                <span>Previous payments <span className="mono">{p.previous_payments}</span></span>
              </div>
            </div>
          </div>

          <div className="rail-item">
            <div className={`rail-node accent ${d ? '' : 'pending'}`}>AI</div>
            <div className="rail-card">
              <div className="rail-kicker">Reasoning {d && <span className="mono" style={{ color: d.source === 'llm' ? 'var(--accent)' : 'var(--text3)' }}>{d.source === 'llm' ? 'gpt-4.1' : 'fallback'}</span>}</div>
              {!d ? <div className="rail-body muted">Not analysed yet.</div> : (
                <div className="rail-body">
                  Recommends <strong>{act(d.recommended_action).toLowerCase()}</strong> — {d.reason.replace(/\.$/, '')}. <span className="conf">Confidence {d.confidence.toFixed(2)}</span>
                  <div style={{ marginTop: 8, color: 'var(--text3)', fontSize: 12.5 }}>{d.diagnosis}</div>
                </div>
              )}
            </div>
          </div>

          <div className="rail-item">
            <div className={`rail-node ${!pol ? 'pending' : blocked ? 'bad' : 'ok'}`}>{!pol ? '' : blocked ? '✕' : '✓'}</div>
            <div className="rail-card">
              <div className="rail-kicker">Policy gate</div>
              {!pol ? <div className="rail-body muted">Waiting for recommendation.</div> : (
                <>
                  <div className="rail-body">
                    {blocked
                      ? <>Recommendation {pol.final_action === 'ESCALATE_TO_HUMAN' || pol.final_action === 'MARK_UNRECOVERABLE' ? 'blocked' : 'downgraded'} — <strong>{act(pol.final_action).toLowerCase()}</strong> instead of {act(d.recommended_action).toLowerCase()}. <span className="muted">{pol.override_reason}</span></>
                      : (() => { const f = pol.checks.filter((x) => !x.passed).length; return <>{pol.checks.length - f} of {pol.checks.length} checks passed{f > 0 && <span className="muted"> ({f} automation gate{f > 1 ? 's' : ''} closed)</span>} — <strong>{act(pol.final_action).toLowerCase()}</strong> approved.</> })()}
                  </div>
                  <div className="policy-grid">
                    {pol.checks.map((ch, i) => {
                      const [okL, badL] = CHECK_LABEL[ch.name] || [ch.name, ch.name]
                      return (
                        <div className="policy-check" key={ch.name} style={{ animationDelay: `${i * 70}ms` }} title={ch.detail}>
                          <div className={`pc-icon ${ch.passed ? 'pass' : 'fail'}`}>{ch.passed ? '✓' : '✕'}</div>
                          <div className={`pc-label ${ch.passed ? '' : 'fail-text'}`}>{ch.passed ? okL : badL}<span className="pc-sub">{ch.detail}</span></div>
                        </div>
                      )
                    })}
                  </div>
                </>
              )}
            </div>
          </div>

          <div className="rail-item">
            <div className={`rail-node ${!ex ? 'pending' : status === 'RECOVERED' ? 'ok' : 'done'}`}>{!ex ? '' : status === 'RECOVERED' ? '✓' : '→'}</div>
            <div className="rail-card">
              <div className="rail-kicker">Action & result</div>
              {!ex ? <div className="rail-body muted">—</div> : (
                <div className="result-row">
                  <div className="rail-body">
                    {status === 'ESCALATED' && <>Routed to <strong>human review</strong> queue.</>}
                    {status === 'RECOVERED' && <><strong>{act(ex.action)}</strong> executed via <span className="mono">{ex.provider}</span> — {ex.detail}.</>}
                    {status === 'UNRESOLVED' && <><strong>{act(ex.action)}</strong> executed via <span className="mono">{ex.provider}</span> — {ex.detail}. {p.attempt_count + 1 >= 2 ? 'Retry budget exhausted; next failure escalates.' : 'One automated attempt remains.'}</>}
                    {status === 'UNRECOVERABLE' && <>No action taken. {p.payment_already_succeeded ? 'Any retry would risk a double charge.' : ex.detail}</>}
                    {ex.reference && <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text3)' }}>ref <span className="mono">{ex.reference}</span> · truth: {act(p.ground_truth_action)} {c.decision_correct ? '✓' : '≠'}</div>}
                  </div>
                  <div className={`result-amt ${resultTone}`}>{resultText}</div>
                </div>
              )}
            </div>
          </div>

        </div>
      </div>
    </>
  )
}
