import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import { Stepper } from './ui'
import Dashboard from './Dashboard'
import PaymentDetails from './PaymentDetails'
import AuditTrail from './AuditTrail'

export default function App() {
  const [view, setView] = useState('dash')
  const [paymentId, setPaymentId] = useState(null)
  const [auditId, setAuditId] = useState('')
  const [metrics, setMetrics] = useState(null)
  const [health, setHealth] = useState(null)
  const [runState, setRunState] = useState(null)
  const [error, setError] = useState(null)
  const [detailStep, setDetailStep] = useState({ active: 5 })
  const timer = useRef(null)

  const refresh = useCallback(async () => {
    try {
      const [m, h] = await Promise.all([api.metrics(), api.health()])
      setMetrics(m); setHealth(h); setError(null)
    } catch (e) { setError(`Backend unreachable: ${e.message}`) }
  }, [])

  useEffect(() => { refresh() }, [refresh])
  useEffect(() => {
    api.status().then((s) => { setRunState(s); if (s.running) startPolling() }).catch(() => {})
    return () => timer.current && clearInterval(timer.current)
  }, [])

  const startPolling = () => {
    if (timer.current) return
    timer.current = setInterval(async () => {
      const s = await api.status().catch(() => null)
      if (!s) return
      setRunState(s)
      await refresh()
      if (!s.running) { clearInterval(timer.current); timer.current = null }
    }, 700)
  }

  const run = async () => {
    try { await api.runBatch({ llm_sample: health?.llm_sample ?? undefined }); setRunState({ running: true, done: 0, total: metrics?.total_payments }); startPolling() } catch (e) { setError(e.message) }
  }
  const reset = async () => { await api.reset(); refresh() }
  const openPayment = (id) => { setPaymentId(id); setView('detail') }
  const openAudit = (id) => { setAuditId(id || ''); setView('audit') }

  const running = !!runState?.running
  const processed = metrics?.processed || 0
  // stepper state per screen
  const stepper = view === 'dash'
    ? { active: running ? 3 : processed ? 5 : 0 }
    : view === 'detail' ? detailStep : { active: 5 }

  const providerLabel = health?.provider === 'razorpay' ? 'rzp_test' : 'rzp_test · simulated'

  return (
    <div className="app">
      <div className="topbar">
        <div className="brand">
          <div className="brand-mark" />
          <div className="brand-name">RecoverAI</div>
          <div className="brand-tag">Payment recovery agent</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div className="nav-tabs">
            <button className={`nav-tab ${view === 'dash' ? 'active' : ''}`} onClick={() => setView('dash')}>Overview</button>
            <button className={`nav-tab ${view === 'detail' ? 'active' : ''}`} onClick={() => (paymentId ? setView('detail') : openPayment('P0099'))}>Payment</button>
            <button className={`nav-tab ${view === 'audit' ? 'active' : ''}`} onClick={() => setView('audit')}>Audit trail</button>
          </div>
          <span className={`env-pill ${health?.llm_enabled ? '' : 'muted'}`} title={health?.llm_enabled ? health.model : 'deterministic fallback'}>
            {health?.llm_enabled ? (health.model || '').replace('openai/', '') : 'fallback'}
          </span>
          <span className="env-pill">{providerLabel}</span>
        </div>
      </div>

      <Stepper active={stepper.active} blocked={stepper.blocked} policyIdx={stepper.policyIdx} />

      {error && <div className="banner-error">{error}</div>}

      {view === 'dash' && (
        <Dashboard metrics={metrics} health={health} running={running} runState={runState} onRun={run} onReset={reset} onOpen={openPayment} />
      )}
      {view === 'detail' && paymentId && (
        <PaymentDetails paymentId={paymentId} onBack={() => setView('dash')} onAudit={openAudit} onChanged={refresh} setStep={setDetailStep} />
      )}
      {view === 'audit' && <AuditTrail paymentId={auditId} onPick={setAuditId} onOpenPayment={openPayment} />}

      <div className="footer">
        <span>LLM proposes · policy engine controls · every step logged before execution.</span>
        <span>
          {[['P0042', 'retry'], ['P0003', 'link'], ['P0099', 'escalate'], ['P0117', 'failed'], ['P0210', 'stale']].map(([id, l]) => (
            <a key={id} href="#" onClick={(e) => { e.preventDefault(); openPayment(id) }} style={{ marginLeft: 14 }}>{id} <span style={{ color: 'var(--text3)' }}>{l}</span></a>
          ))}
        </span>
      </div>
    </div>
  )
}
