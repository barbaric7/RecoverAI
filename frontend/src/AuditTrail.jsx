import { useEffect, useState } from 'react'
import { api } from './api'

const fmt = (ts) => {
  const d = new Date(ts)
  return d.toLocaleTimeString('en-IN', { hour12: false }) + '.' + String(d.getMilliseconds()).padStart(3, '0')
}

export default function AuditTrail({ paymentId, onPick, onOpenPayment }) {
  const [items, setItems] = useState([])
  const [q, setQ] = useState(paymentId || '')
  const [expanded, setExpanded] = useState({})

  useEffect(() => { setQ(paymentId || '') }, [paymentId])
  useEffect(() => {
    const id = q.trim().toUpperCase()
    const valid = /^P\d{4}$/.test(id)
    api.audit(valid ? id : undefined, 150).then((r) => {
      const rows = r.items
      setItems(rows)
    })
  }, [q])

  const validId = /^P\d{4}$/.test(q.trim().toUpperCase())

  return (
    <>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="flex between">
          <div>
            <h3 style={{ margin: 0 }}>Audit trail {validId && <span className="mono" style={{ color: 'var(--text)' }}>· {q.toUpperCase()}</span>}</h3>
            <div className="muted" style={{ fontSize: 12 }}>Every decision step is logged before any action is taken. {!validId && 'Showing the most recent 150 events across all payments.'}</div>
          </div>
          <div className="flex">
            <input className="search" style={{ width: 200 }} placeholder="Payment id, e.g. P0042" value={q} onChange={(e) => { setQ(e.target.value); onPick?.(e.target.value) }} />
            {validId && <button className="small" onClick={() => onOpenPayment(q.toUpperCase())}>Open payment</button>}
            {q && <button className="small ghost" onClick={() => { setQ(''); onPick?.('') }}>Clear</button>}
          </div>
        </div>
      </div>

      <div className="card">
        {items.length === 0 ? (
          <div className="empty">No audit events yet. Run recovery first.</div>
        ) : (
          <div className="timeline">
            {items.map((e, i) => {
              const key = `${e.payment_id}-${i}`
              const open = expanded[key]
              return (
                <div key={key} className={`tl ${e.step}`}>
                  <div className="flex" style={{ gap: 12 }}>
                    <span className="t">{fmt(e.ts)}</span>
                    {!validId && <button className="small ghost mono" onClick={() => { setQ(e.payment_id); onPick?.(e.payment_id) }}>{e.payment_id}</button>}
                    <span className="step">{e.step}</span>
                    <span className="m">{e.message}</span>
                    {['REASON', 'DECIDE', 'POLICY'].includes(e.step) && <span className="pre-badge">logged before execution</span>}
                    {e.data && <button className="small ghost" onClick={() => setExpanded({ ...expanded, [key]: !open })}>{open ? 'hide' : 'details'}</button>}
                  </div>
                  {open && <pre>{JSON.stringify(e.data, null, 2)}</pre>}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </>
  )
}
