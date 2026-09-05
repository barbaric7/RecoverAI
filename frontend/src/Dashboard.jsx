import { useEffect, useRef, useState } from 'react'
import { api, inr, inrFull, pct, title } from './api'
import { Count, Pipeline } from './ui'

function Kpi({ label, value, format, sub, tone }) {
  return (
    <div className={`card kpi ${tone || ''}`}>
      <h3>{label}</h3>
      <div className="value"><Count value={value || 0} format={format} /></div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  )
}

const STATUS_COLORS = {
  RECOVERED: 'var(--green)',
  ESCALATED: 'var(--amber)',
  UNRESOLVED: '#64748b',
  UNRECOVERABLE: 'var(--red)',
}

export default function Dashboard({ metrics, health, running, runState, onRun, onReset, onOpen }) {
  const m = metrics
  const [recent, setRecent] = useState([])
  const [filter, setFilter] = useState('')
  const [q, setQ] = useState('')

  const seen = useRef(new Set())
  useEffect(() => {
    let dead = false
    api.cases(filter || undefined).then((r) => {
      if (dead) return
      const items = running ? [...r.items].reverse() : r.items
      setRecent(items.map((c) => ({ ...c, fresh: running && !seen.current.has(c.payment_id) })))
      items.forEach((c) => seen.current.add(c.payment_id))
    })
    return () => { dead = true }
  }, [filter, m?.processed, running])
  useEffect(() => { if (running) seen.current = new Set() }, [running])

  const processed = m?.processed || 0
  const total = m?.total_payments || 0
  const funnel = [
    ['Processed', processed, '#60a5fa'],
    ['Recoverable', m?.recoverable_count, '#a78bfa'],
    ['Recovered', m?.recovered_count, STATUS_COLORS.RECOVERED],
    ['Escalated', m?.escalated_count, STATUS_COLORS.ESCALATED],
    ['Unresolved', m?.unresolved_count, STATUS_COLORS.UNRESOLVED],
    ['Unrecoverable', m?.unrecoverable_count, STATUS_COLORS.UNRECOVERABLE],
  ]
  const icons = { Processed: '▶', Recoverable: '◆', Recovered: '✓', Escalated: '→', Unresolved: '○', Unrecoverable: '!' }

  const shown = recent.filter((c) => !q || c.payment_id.toLowerCase().includes(q.toLowerCase())).slice(0, 60)

  const overrideEntries = Object.entries(m?.policy_override_breakdown || {}).sort((a, b) => b[1] - a[1])
  const reasonRows = Object.entries(m?.by_failure_reason || {}).sort((a, b) => b[1].at_risk - a[1].at_risk)

  return (
    <>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="flex between">
          <div>
            <div style={{ fontSize: 16, fontWeight: 700 }}>
              {total} failed payment events · {inrFull(m?.at_risk_amount)} at risk
            </div>
            <div className="muted" style={{ fontSize: 12 }}>
              Agent brain: {health?.llm_enabled ? <span className="pill llm">LLM · {health.model}</span> : <span className="pill fallback">deterministic fallback (no OPENAI_API_KEY)</span>}
              {' '}· Provider: <span className="mono">{health?.provider || '…'}</span>
              {' '}· Loop: Observe → Reason → Policy → Act → Verify → Audit
            </div>
          </div>
          <div className="flex">
            <button className="ghost" onClick={onReset} disabled={running}>Reset</button>
            <button className="primary" onClick={onRun} disabled={running}>
              {running ? `Running… ${runState?.done || 0}/${runState?.total || 0}` : processed ? 'Re-run Recovery' : '▶ Run Recovery'}
            </button>
          </div>
        </div>
        <div style={{ marginTop: 14 }}><Pipeline done={processed ? 5 : -1} labels={{ OBSERVE: 'Payment + history', REASON: 'LLM proposes', POLICY: 'Policy controls', ACT: 'Razorpay (test)', VERIFY: 'Outcome', AUDIT: 'Audit + metrics' }} /></div>
        {running && (
          <div className="progress"><i style={{ width: `${runState?.total ? (100 * runState.done) / runState.total : 0}%` }} /></div>
        )}
      </div>

      <div className="grid kpis" style={{ marginBottom: 16 }}>
        <Kpi label="At Risk" value={m?.at_risk_amount} format={inr} sub={`${total} failed payments`} />
        <Kpi label="Recovered" value={m?.recovered_amount} format={inr} sub={`${m?.recovered_count || 0} payments`} tone="green" />
        <Kpi label="Recovery Rate" value={m?.recovery_rate} format={pct} sub="recovered ÷ recoverable" tone="blue" />
        <Kpi label="Decision Accuracy" value={m?.decision_accuracy} format={pct} sub={`vs ground truth · ${m?.policy_overrides || 0} policy overrides`} />
        <Kpi label="Escalated" value={m?.escalated_count} format={(v) => Math.round(v)} sub={`${inr(m?.escalated_amount)} needs human review`} tone="amber" />
      </div>

      <div className="grid two" style={{ marginBottom: 16 }}>
        <div className="card">
          <h3>{processed} Payments Processed</h3>
          <div className="funnel">
            {funnel.map(([label, n, color]) => (
              <div className="row" key={label}>
                <span style={{ color }}>{icons[label]}</span>
                <span>{label}</span>
                <div className="bar"><i style={{ width: `${total ? (100 * (n || 0)) / total : 0}%`, background: color }} /></div>
                <span className="n">{n ?? 0}</span>
              </div>
            ))}
          </div>
          {processed > 0 && (
            <div className="muted" style={{ fontSize: 12, marginTop: 12 }}>
              {m.auto_handled} handled automatically · attempt success {pct(m.attempt_success_rate)} · LLM decisions {m.llm_decisions} / fallback {m.fallback_decisions}
            </div>
          )}
        </div>

        <div className="card">
          <h3>LLM proposes · Policy engine controls</h3>
          {processed === 0 ? (
            <div className="empty">Run recovery to see policy activity</div>
          ) : (
            <>
              <div className="kv" style={{ marginBottom: 12 }}>
                <dt>Raw LLM accuracy</dt><dd>{pct(m.llm_raw_accuracy)}</dd>
                <dt>After policy gate</dt><dd style={{ color: 'var(--green)', fontWeight: 600 }}>{pct(m.decision_accuracy)}</dd>
                <dt>Actions blocked / downgraded</dt><dd>{m.policy_overrides}</dd>
              </div>
              {overrideEntries.length > 0 ? (
                <table>
                  <thead><tr><th>Override</th><th className="num">Count</th></tr></thead>
                  <tbody>
                    {overrideEntries.map(([k, v]) => (
                      <tr key={k}><td className="mono">{k}</td><td className="num">{v}</td></tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="banner ok">Every LLM recommendation stayed within policy on this run.</div>
              )}
            </>
          )}
        </div>
      </div>

      {reasonRows.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h3>Recovery by failure reason</h3>
          <div className="bars">
            {reasonRows.map(([r, v]) => (
              <div className="row" key={r}>
                <span>{title(r)} <span className="tag">({v.count})</span></span>
                <div className="bar"><i style={{ width: `${v.count ? (100 * v.recovered) / v.count : 0}%` }} /></div>
                <span className="right mono">{v.recovered}/{v.count} · {inr(v.amount_recovered)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="card">
        <div className="flex between" style={{ marginBottom: 12 }}>
          <h3 style={{ margin: 0 }}>Agent decisions {running && <span className="live" style={{ marginLeft: 8 }}>LIVE · streaming</span>}</h3>
          <div className="flex filters">
            <input className="search" style={{ width: 160 }} placeholder="Find P0042…" value={q} onChange={(e) => setQ(e.target.value)} />
            {['', 'RECOVERED', 'ESCALATED', 'UNRESOLVED', 'UNRECOVERABLE'].map((s) => (
              <button key={s} className={filter === s ? 'active' : ''} onClick={() => setFilter(s)}>{s || 'All'}</button>
            ))}
          </div>
        </div>
        {shown.length === 0 ? (
          <div className="empty">{processed ? 'No cases match' : 'No decisions yet — click Run Recovery'}</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Payment</th><th className="num">Amount</th><th>Failure</th><th>LLM proposed</th><th>Policy</th><th>Executed</th><th className="num">Conf.</th><th>Status</th><th className="num">Recovered</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((c) => (
                <tr key={c.payment_id} className={`click ${c.fresh ? 'fresh' : ''}`} onClick={() => onOpen(c.payment_id)}>
                  <td className="mono">{c.payment_id}</td>
                  <td className="num money">{inrFull(c.amount)}</td>
                  <td>{title(c.failure_reason)}</td>
                  <td><span className="pill action">{c.recommended_action}</span></td>
                  <td>{c.policy_allowed ? <span style={{ color: 'var(--green)' }}>✓ allowed</span> : <span style={{ color: 'var(--amber)' }}>⛔ overridden</span>}</td>
                  <td><span className="pill action">{c.final_action}</span></td>
                  <td className="num">{Math.round(c.confidence * 100)}%</td>
                  <td><span className={`pill ${c.status}`}>{c.status}</span></td>
                  <td className="num money" style={{ color: c.amount_recovered ? 'var(--green)' : 'var(--muted)' }}>{c.amount_recovered ? inrFull(c.amount_recovered) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {recent.length > 60 && <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>Showing 60 of {recent.length}. Use search to find a specific payment.</div>}
      </div>
    </>
  )
}
