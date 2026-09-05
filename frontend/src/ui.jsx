import { useEffect, useRef, useState } from 'react'

export function useCountUp(value, ms = 600) {
  const [v, setV] = useState(value ?? 0)
  const from = useRef(value ?? 0)
  useEffect(() => {
    const a = from.current, b = value ?? 0
    if (a === b) return
    const start = performance.now()
    let raf
    const step = (t) => {
      const k = Math.min(1, (t - start) / ms)
      const e = 1 - Math.pow(1 - k, 3)
      setV(a + (b - a) * e)
      if (k < 1) raf = requestAnimationFrame(step); else from.current = b
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [value, ms])
  return v
}

export function Count({ value, format }) {
  const v = useCountUp(value)
  return <>{format ? format(v) : Math.round(v)}</>
}

export const STEPS = ['Observe', 'Reason', 'Policy gate', 'Act', 'Verify', 'Audit']

/**
 * Persistent pipeline stepper (recurring motif).
 * active: index of the active step; steps before it are "done".
 * blocked: paints the active step in danger colour (policy override).
 */
export function Stepper({ active = 2, blocked = false, policyIdx = 2 }) {
  return (
    <div className="stepper">
      {STEPS.map((label, i) => {
        const cls = ['step']
        if (i < active) cls.push('done')
        if (i === active) cls.push('active')
        if (blocked && i === policyIdx && i <= active) cls.push('blocked')
        return (
          <div key={label} style={{ display: 'contents' }}>
            <div className={cls.join(' ')}>
              <div className="step-dot" />
              <div className="step-label">{label}</div>
            </div>
            {i < STEPS.length - 1 && <div className={`step-line ${i < active ? 'done' : ''}`} />}
          </div>
        )
      })}
    </div>
  )
}

export const STATUS_BADGE = {
  RECOVERED: ['badge-success', 'Recovered'],
  ESCALATED: ['badge-neutral', 'Escalated'],
  UNRESOLVED: ['badge-danger', 'Unresolved'],
  UNRECOVERABLE: ['badge-neutral', 'No action'],
  PENDING: ['badge-warn', 'Pending'],
  WAITING: ['badge-warn', 'Waiting'],
}

export function Badge({ status }) {
  const [cls, label] = STATUS_BADGE[status] || ['badge-neutral', status]
  return <span className={`badge ${cls}`}><span className="badge-dot" />{label}</span>
}

export const ACTION_LABEL = {
  RETRY_PAYMENT: 'Retry',
  CREATE_PAYMENT_LINK: 'Payment link',
  WAIT_AND_RETRY: 'Wait + retry',
  ESCALATE_TO_HUMAN: 'Escalate',
  MARK_UNRECOVERABLE: 'No action',
}
export const act = (a) => ACTION_LABEL[a] || a
