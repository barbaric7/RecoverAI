import { useEffect, useState } from 'react'
import { api, inrFull, title } from './api'
import { Pipeline } from './ui'

export default function PaymentDetails({ paymentId, onBack, onAudit, onChanged }) {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const load = () => api.payment(paymentId).then(setData).catch((e) => setErr(String(e)))
  useEffect(() => { setData(null); load() }, [paymentId])

  const run = async () => {
    setBusy(true)
    try { await api.runOne(paymentId); await load(); onChanged?.() } catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }

  if (err) return <div className="banner bad">{err}</div>
  if (!data) return <div className="empty">Loading…</div>

  const p = data.payment
  const c = data.case
  const d = c?.decision
  const pol = c?.policy
  const ex = c?.execution
  const status = c?.status || 'PENDING'
  const succ = Math.round(p.customer_success_rate * p.previous_payments)

  const done = !c ? 0 : 5
  const blocked = !!pol && !pol.allowed

  return (
    <>
      <div className="flex between" style={{ marginBottom: 12 }}>
        <div className="flex">
          <button className="ghost" onClick={onBack}>← Back</button>
          <div>
            <div style={{ fontSize: 20, fontWeight: 700 }} className="mono">PAYMENT {p.payment_id}</div>
            <div className="muted" style={{ fontSize: 12 }}>Customer {p.customer_id} · {p.currency}</div>
          </div>
        </div>
        <div className="flex">
          <span className={`pill ${status}`}>{status}</span>
          <button onClick={() => onAudit(p.payment_id)} disabled={!c}>Audit trail</button>
          <button className="primary" onClick={run} disabled={busy}>{busy ? 'Running…' : c ? 'Re-run agent' : '▶ Run agent on this payment'}</button>
        </div>
      </div>

      <Pipeline done={done} blockedAtPolicy={blocked} />

      <div className="detail-grid">
        <div className="card">
          <h3>Failed payment</h3>
          <div className="big">{inrFull(p.amount)}</div>
          <dl className="kv" style={{ marginTop: 10 }}>
            <dt>Failure</dt><dd>{title(p.failure_reason)}<div className="muted" style={{ fontSize: 12 }}>{p.failure_message}</div></dd>
            <dt>Attempts so far</dt><dd>{p.attempt_count}</dd>
            <dt>Prev. recovery attempts</dt><dd>{p.previous_recovery_attempts}</dd>
            <dt>Time since failure</dt><dd>{p.days_since_failure < 1 ? `${Math.round(p.days_since_failure * 24)}h` : `${p.days_since_failure}d`}</dd>
            <dt>Subscription</dt><dd>{title(p.subscription_status)}</dd>
            {p.payment_already_succeeded && <><dt>⚠ Stale event</dt><dd style={{ color: 'var(--amber)' }}>Payment already succeeded</dd></>}
          </dl>
          <h3 style={{ marginTop: 18 }}>Customer history</h3>
          <dl className="kv">
            <dt>Previous payments</dt><dd>{p.previous_payments}</dd>
            <dt>Successful</dt><dd>{succ} ({Math.round(p.customer_success_rate * 100)}%)</dd>
          </dl>
        </div>

        <div className="card ai">
          <h3>AI diagnosis {d && <span className={`pill ${d.source}`} style={{ marginLeft: 6 }}>{d.source === 'llm' ? 'LLM' : 'fallback'}</span>}</h3>
          {!d ? (
            <div className="empty">Not analysed yet</div>
          ) : (
            <>
              <div style={{ fontSize: 15, marginBottom: 12 }}>{d.diagnosis}</div>
              <dl className="kv">
                <dt>Recoverable</dt><dd>{d.recoverable ? 'Yes' : 'No'}</dd>
                <dt>Confidence</dt>
                <dd>
                  <div className="flex"><span style={{ width: 40 }}>{Math.round(d.confidence * 100)}%</span><div className="conf" style={{ flex: 1 }}><i style={{ width: `${d.confidence * 100}%` }} /></div></div>
                </dd>
                <dt>Expected recovery</dt><dd>{inrFull(d.expected_recovery)}</dd>
                <dt>Recommended action</dt><dd><span className="pill action">{d.recommended_action}</span></dd>
                <dt>Reason</dt><dd>{d.reason}</dd>
              </dl>
              {d.policy_checks?.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <div className="tag" style={{ marginBottom: 4 }}>Rules the agent says it considered</div>
                  <ul className="muted" style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>
                    {d.policy_checks.map((x, i) => <li key={i}>{x}</li>)}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>

        <div className={`card policy ${blocked ? 'blocked' : ''}`}>
          <h3>Policy engine <span className="tag" style={{ textTransform: 'none', letterSpacing: 0 }}>· deterministic · runs before any money moves</span></h3>
          {!pol ? (
            <div className="empty">—</div>
          ) : (
            <>
              {pol.allowed ? (
                <div className="banner ok animate" style={{ marginBottom: 10, animationDelay: `${(pol.checks.length) * 120}ms` }}>✓ Policy validation passed — <b>{pol.final_action}</b> approved</div>
              ) : (
                <div className="banner warn animate" style={{ marginBottom: 10, animationDelay: `${(pol.checks.length) * 120}ms` }}>
                  ⛔ <b>{d.recommended_action}</b> blocked → executing <b>{pol.final_action}</b>
                  <div style={{ marginTop: 4, fontSize: 12 }}>{pol.override_reason}</div>
                </div>
              )}
              {pol.checks.map((ch, i) => (
                <div key={ch.name} className={`check ${ch.passed ? 'ok' : 'bad'}`} style={{ animationDelay: `${i * 120}ms` }}>
                  <span className="icon">{ch.passed ? '✓' : '✕'}</span>
                  <div>
                    <div className="name">{ch.name}</div>
                    <div className="d">{ch.detail}</div>
                  </div>
                </div>
              ))}
            </>
          )}
        </div>

        <div className={`card result ${status === 'RECOVERED' ? 'ok' : ''}`}>
          <h3>Action & result</h3>
          {!ex ? (
            <div className="empty">—</div>
          ) : (
            <>
              <div className="banner info animate" style={{ marginBottom: 10 }}>
                <b>[ {ex.action.replaceAll('_', ' ')} {ex.executed ? 'EXECUTED' : 'SKIPPED'} ]</b>
                <div style={{ fontSize: 12, marginTop: 4 }}>via <span className="mono">{ex.provider}</span>{ex.reference && <> · ref <span className="mono">{ex.reference}</span></>}</div>
              </div>
              <dl className="kv">
                <dt>Outcome</dt><dd><span className={`pill ${status}`}>{ex.outcome}</span></dd>
                <dt>Detail</dt><dd>{ex.detail}</dd>
                <dt>Decision vs truth</dt><dd>{c.decision_correct ? <span style={{ color: 'var(--green)' }}>✓ matches ground truth ({p.ground_truth_action})</span> : <span style={{ color: 'var(--amber)' }}>differs (truth: {p.ground_truth_action})</span>}</dd>
              </dl>
              {status === 'RECOVERED' && <div className="big recovered-flash" style={{ color: 'var(--green)', marginTop: 12 }}>✓ {inrFull(ex.amount_recovered)} recovered</div>}
              {status === 'ESCALATED' && <div className="big" style={{ color: 'var(--amber)', marginTop: 12, fontSize: 18 }}>→ Human review required</div>}
              {status === 'UNRESOLVED' && <div className="big" style={{ color: '#cbd5e1', marginTop: 12, fontSize: 18 }}>○ Not recovered — {p.attempt_count + 1 >= 2 ? 'retry budget exhausted; next failure escalates' : 'eligible for one more automated attempt'}</div>}
              {status === 'UNRECOVERABLE' && <div className="big" style={{ color: 'var(--red)', marginTop: 12, fontSize: 18 }}>! Stopped — no further automated action</div>}
            </>
          )}
        </div>
      </div>
    </>
  )
}
