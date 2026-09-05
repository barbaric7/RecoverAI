import { useEffect, useRef, useState } from 'react'

/** Animated number: eases from previous value to `value`. */
export function useCountUp(value, ms = 700) {
  const [v, setV] = useState(value ?? 0)
  const from = useRef(value ?? 0)
  useEffect(() => {
    const start = performance.now()
    const a = from.current
    const b = value ?? 0
    if (a === b) return
    let raf
    const step = (t) => {
      const k = Math.min(1, (t - start) / ms)
      const e = 1 - Math.pow(1 - k, 3)
      setV(a + (b - a) * e)
      if (k < 1) raf = requestAnimationFrame(step)
      else from.current = b
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

/**
 * The architecture as UI. stage: index of the last completed stage (0..5),
 * blockedAtPolicy: paint the POLICY node red-ish when it overrode the LLM.
 */
export const STAGES = ['OBSERVE', 'REASON', 'POLICY', 'ACT', 'VERIFY', 'AUDIT']
const LABELS = { OBSERVE: 'Failure + history', REASON: 'AI diagnosis', POLICY: 'Policy gate', ACT: 'Execute', VERIFY: 'Outcome', AUDIT: 'Recorded' }

export function Pipeline({ done = -1, blockedAtPolicy = false, labels = LABELS }) {
  return (
    <div className="pipeline">
      {STAGES.map((s, i) => {
        const cls = ['st']
        if (s === 'REASON') cls.push('ai')
        if (s === 'POLICY') cls.push('policy')
        if (i <= done) cls.push('done'); else cls.push('pending')
        if (s === 'POLICY' && blockedAtPolicy && i <= done) cls.push('blocked')
        return (
          <div key={s} className={cls.join(' ')}>
            {s}
            <span className="lbl">{labels[s]}</span>
          </div>
        )
      })}
    </div>
  )
}
