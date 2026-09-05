import { useEffect, useRef, useState } from 'react'
import { api, inrFull, title } from './api'
import { Badge, Count, act } from './ui'

const FILTERS = [['', 'All'], ['RECOVERED', 'Recovered'], ['ESCALATED', 'Escalated'], ['UNRESOLVED', 'Unresolved'], ['UNRECOVERABLE', 'No action']]

export default function Dashboard({ metrics: m, health, running, runState, onRun, onReset, onOpen }) {
  const [rows, setRows] = useState([])
  const [filter, setFilter] = useState('')
  const [q, setQ] = useState('')
  const seen = useRef(new Set())

  useEffect(() => { if (running) seen.current = new Set() }, [running])
  useEffect(() => {
    let dead = false
    api.cases(filter || undefined).then((r) => {
      if (dead) return
      const items = running ? [...r.items].reverse() : r.items
      setRows(items.map((c) => ({ ...c, fresh: running && !seen.current.has(c.payment_id) })))
      items.forEach((c) => seen.current.add(c.payment_id))
    })
    return () => { dead = true }
  }, [filter, m?.processed, running])

  const processed = m?.processed || 0
  const total = m?.total_payments || 0
  const shown = rows.filter((c) => !q || c.payment_id.toLowerCase().includes(q.toLowerCase())).slice(0, 80)
  const overrides = Object.entries(m?.policy_override_breakdown || {}).sort((a, b) => b[1] - a[1])
  const reasons = Object.entries(m?.by_failure_reason || {}).sort((a, b) => b[1].count - a[1].count)
  const pctOf = (n, d) => (d ? (100 * n) / d : 0)

  return (
    <>
      <div className="kpi-row">
        <div className="kpi">
          <div className="kpi-label">Revenue at risk</div>
          <div className="kpi-value"><Count value={m?.at_risk_amount} format={inrFull} /></div>
          <div className="kpi-sub">{total} failed payments</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Recovered</div>
          <div className="kpi-value"><Count value={m?.recovered_amount} format={inrFull} /></div>
          <div className="kpi-sub up">{m?.recovered_count || 0} payments · {(m?.recovery_rate || 0).toFixed(1)}%</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Escalated to review</div>
          <div className="kpi-value"><Count value={m?.escalated_count} /></div>
          <div className="kpi-sub">{inrFull(m?.escalated_amount)} routed</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Policy overrides</div>
          <div className="kpi-value"><Count value={m?.policy_overrides} /></div>
          <div className="kpi-sub">blocked or downgraded</div>
        </div>
      </div>

      {running && (
        <div className="progress"><i style={{ width: `${runState?.total ? (100 * runState.done) / runState.total : 0}%` }} /></div>
      )}

      {processed > 0 && (
        <div className="two-col">
          <div>
            <div className="section-head"><div className="section-title">Outcomes</div><span className="conf">{processed} / {total} processed</span></div>
            <div className="stat-list">
              {[
                ['Recoverable', m.recoverable_count, ''],
                ['Recovered', m.recovered_count, 'ok'],
                ['Escalated', m.escalated_count, 'warn'],
                ['Unresolved', m.unresolved_count, ''],
                ['No action', m.unrecoverable_count, 'bad'],
              ].map(([l, n, tone]) => (
                <div className="stat-row" key={l}>
                  <span>{l}</span>
                  <div className="bar"><i className={tone} style={{ width: `${pctOf(n, total)}%` }} /></div>
                  <span className="n">{n}</span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="section-head"><div className="section-title">LLM proposes · policy controls</div><span className="conf">{m.llm_decisions} llm / {m.fallback_decisions} fallback</span></div>
            <div className="callout-row">
              <div className="callout">Raw LLM accuracy<div className="big">{m.llm_raw_accuracy.toFixed(1)}%</div>vs ground truth</div>
              <div className="callout">After policy gate<div className="big ok">{m.decision_accuracy.toFixed(1)}%</div>{m.policy_overrides} overrides</div>
            </div>
            {overrides.length > 0 && (
              <div className="stat-list" style={{ marginTop: 8 }}>
                {overrides.slice(0, 5).map(([k, v]) => {
                  const [from, to] = k.split(' → ')
                  return (
                    <div className="stat-row" key={k} style={{ gridTemplateColumns: '1fr 56px' }}>
                      <span className="mono" style={{ fontSize: 12 }}>{act(from)} <span style={{ color: 'var(--text3)' }}>→</span> {act(to)}</span>
                      <span className="n">{v}</span>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {reasons.length > 0 && (
        <div style={{ marginBottom: 28 }}>
          <div className="section-head"><div className="section-title">Recovery by failure reason</div></div>
          <div className="stat-list">
            {reasons.map(([r, v]) => (
              <div className="stat-row" key={r} style={{ gridTemplateColumns: '170px 1fr 150px' }}>
                <span>{title(r)} <span style={{ color: 'var(--text3)' }}>· {v.count}</span></span>
                <div className="bar"><i className="ok" style={{ width: `${pctOf(v.recovered, v.count)}%` }} /></div>
                <span className="n">{v.recovered}/{v.count} · {inrFull(v.amount_recovered)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="section-head">
        <div className="section-title">Decisions {running && <span className="live">live · {runState?.done}/{runState?.total}</span>}</div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {processed > 0 && (
            <div className="filters" style={{ marginRight: 8 }}>
              <input className="search" placeholder="P0042" value={q} onChange={(e) => setQ(e.target.value)} />
              {FILTERS.map(([v, l]) => <button key={v} className={`chip ${filter === v ? 'active' : ''}`} onClick={() => setFilter(v)}>{l}</button>)}
            </div>
          )}
          <button className="btn-ghost" onClick={onReset} disabled={running}>Reset run</button>
          <button className="btn" onClick={onRun} disabled={running}>{running ? 'Running…' : 'Run recovery'}</button>
        </div>
      </div>

      {shown.length === 0 ? (
        <div className="empty">{processed ? 'No decisions match.' : `${total} failed payments · ${inrFull(m?.at_risk_amount)} at risk. Run recovery to start the agent.`}</div>
      ) : (
        <table>
          <thead>
            <tr><th>Payment</th><th>Amount</th><th>Failure reason</th><th>Confidence</th><th>Recommended</th><th>Final action</th><th>Outcome</th><th style={{ textAlign: 'right' }}>Recovered</th></tr>
          </thead>
          <tbody>
            {shown.map((c) => (
              <tr key={c.payment_id} className={c.fresh ? 'fresh' : ''} onClick={() => onOpen(c.payment_id)}>
                <td className="id">{c.payment_id}</td>
                <td className="amt">{inrFull(c.amount)}</td>
                <td>{c.failure_reason === 'PAYMENT_TIMEOUT' && c.final_action === 'MARK_UNRECOVERABLE' ? 'Stale event' : title(c.failure_reason)}</td>
                <td className="conf">{c.confidence.toFixed(2)}</td>
                <td>{act(c.recommended_action)}</td>
                <td className={c.policy_allowed ? '' : 'overridden'}>{c.policy_allowed ? act(c.final_action) : (c.final_action === 'MARK_UNRECOVERABLE' ? 'Blocked' : act(c.final_action))}</td>
                <td><Badge status={c.status} /></td>
                <td className={`amt ${c.amount_recovered ? 'up' : ''}`} style={{ textAlign: 'right', color: c.amount_recovered ? undefined : 'var(--text3)' }}>{c.amount_recovered ? inrFull(c.amount_recovered) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {rows.length > 80 && <div className="note">Showing 80 of {rows.length}. Filter or search by payment id.</div>}
    </>
  )
}
