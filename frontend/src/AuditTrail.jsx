import { useEffect, useState } from 'react'
import { api } from './api'
import { act } from './ui'

const fmt = (ts) => new Date(ts).toLocaleTimeString('en-IN', { hour12: false })
const isId = (s) => /^P\d{4}$/.test((s || '').trim().toUpperCase())

const EVENT_TITLE = {
  EVENT: 'Failed payment observed',
  OBSERVE: 'Customer history retrieved',
  REASON: 'Agent reasoning complete',
  DECIDE: 'Strategy selected',
  POLICY: null, // computed
  ACT: null,
  VERIFY: null,
  OUTCOME: null,
}

function describe(e) {
  const d = e.data || {}
  switch (e.step) {
    case 'EVENT':
      return ['Failed payment observed', <>{(d.failure_reason || '').replaceAll('_', ' ').toLowerCase()} · <span className="mono">₹{Math.round(d.amount || 0).toLocaleString('en-IN')}</span></>, '']
    case 'OBSERVE':
      return ['Customer history retrieved', <><span className="mono">{d.previous_payments}</span> payments · success <span className="mono">{Math.round((d.success_rate || 0) * 100)}%</span> · attempt <span className="mono">{d.attempt_count} of 2</span></>, '']
    case 'REASON':
      return ['Agent reasoning complete', <>{d.diagnosis}</>, '']
    case 'DECIDE': {
      const a = e.message.split(': ')[1]
      return ['Strategy selected', <>Recommended <span className="mono">{act(a).toLowerCase()}</span>{d.reason && <> · {d.reason}</>}</>, '']
    }
    case 'POLICY': {
      const checks = d.checks || []
      const failed = checks.filter((c) => !c.passed)
      const blocked = e.message.startsWith('Policy BLOCKED')
      return [
        blocked ? `Policy gate — overrode recommendation` : `Policy gate — ${checks.length} checks passed`,
        <>{checks.map((c) => <span key={c.name} style={{ marginRight: 10 }}><span className="mono">{c.name}</span> <span className={c.passed ? 'ok' : 'bad'}>{c.passed ? '✓' : '✕'}</span></span>)}{blocked && <div style={{ color: 'var(--danger)' }}>{d.override_reason}</div>}</>,
        blocked ? 'bad' : failed.length ? '' : 'ok',
      ]
    }
    case 'ACT': {
      const a = e.message.split(' executed via ')[0]
      const via = e.message.split(' executed via ')[1]
      return [`${act(a)} executed`, <>via <span className="mono">{via}</span>{d.reference && <> · ref <span className="mono">{d.reference}</span></>} · logged before execution</>, 'action']
    }
    case 'VERIFY': {
      const o = e.message.split(': ')[1]
      return [`Verified — ${o === 'SUCCESS' ? 'payment succeeded' : o === 'ESCALATED' ? 'in review queue' : o === 'SKIPPED' ? 'no action taken' : o === 'EXPIRED' ? 'link expired' : 'payment failed'}`, <>outcome <span className="mono">{o}</span></>, o === 'SUCCESS' ? 'ok' : o === 'FAIL' || o === 'EXPIRED' ? 'bad' : '']
    }
    case 'OUTCOME': {
      const m = e.message.match(/₹[\d,]+/)
      return [m ? 'Revenue recovered' : e.message, m ? <><span className="mono ok">{m[0]}</span> added to recovered revenue</> : null, m ? 'ok' : '']
    }
    default:
      return [e.message, null, '']
  }
}

export default function AuditTrail({ paymentId, onPick, onOpenPayment }) {
  const [items, setItems] = useState([])
  const [q, setQ] = useState(paymentId || '')
  const [kind, setKind] = useState('all')
  const [open, setOpen] = useState({})

  useEffect(() => { setQ(paymentId || '') }, [paymentId])
  useEffect(() => {
    const id = q.trim().toUpperCase()
    api.audit(isId(id) ? id : undefined, 120).then((r) => setItems(r.items))
  }, [q])

  const single = isId(q)
  const filtered = items.filter((e) => kind === 'all' || (kind === 'policy' && e.step === 'POLICY') || (kind === 'actions' && ['ACT', 'VERIFY', 'OUTCOME'].includes(e.step)))

  return (
    <>
      <div className="section-head">
        <div className="section-title">Audit trail · <span className="mono">{single ? q.toUpperCase() : 'latest events'}</span></div>
        <div className="audit-filter">
          <input className="search" placeholder="P0042" value={q} onChange={(e) => { setQ(e.target.value); onPick?.(e.target.value) }} />
          {[['all', 'All events'], ['policy', 'Policy checks'], ['actions', 'Actions']].map(([k, l]) => (
            <button key={k} className={`chip ${kind === k ? 'active' : ''}`} onClick={() => setKind(k)}>{l}</button>
          ))}
          {single && <button className="btn-ghost btn-sm" onClick={() => onOpenPayment(q.toUpperCase())}>Open payment</button>}
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="empty">No audit events yet. Run recovery first.</div>
      ) : (
        <div className="timeline">
          {filtered.map((e, i) => {
            const [titleTxt, detail, tone] = describe(e)
            const key = `${e.payment_id}-${i}`
            return (
              <div className="t-item" key={key}>
                <div className={`t-dot ${tone}`} />
                <div className="t-row">
                  <span className="t-time">{fmt(e.ts)}</span>
                  {!single && <button className="t-pid" onClick={() => { setQ(e.payment_id); onPick?.(e.payment_id) }}>{e.payment_id}</button>}
                  <span className="t-event">{titleTxt}</span>
                  {e.data && <button className="t-more" onClick={() => setOpen({ ...open, [key]: !open[key] })}>{open[key] ? 'hide' : 'raw'}</button>}
                </div>
                {detail && <div className="t-detail">{detail}</div>}
                {open[key] && <div className="t-detail"><pre>{JSON.stringify(e.data, null, 2)}</pre></div>}
              </div>
            )
          })}
        </div>
      )}
    </>
  )
}
