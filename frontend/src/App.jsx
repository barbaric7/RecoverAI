import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import Dashboard from './Dashboard'
import PaymentDetails from './PaymentDetails'
import AuditTrail from './AuditTrail'

export default function App() {
  const [view, setView] = useState('overview') // overview | payment | audit
  const [paymentId, setPaymentId] = useState(null)
  const [auditId, setAuditId] = useState('')
  const [metrics, setMetrics] = useState(null)
  const [health, setHealth] = useState(null)
  const [runState, setRunState] = useState(null)
  const [error, setError] = useState(null)
  const timer = useRef(null)

  const refresh = useCallback(async () => {
    try {
      const [m, h] = await Promise.all([api.metrics(), api.health()])
      setMetrics(m); setHealth(h); setError(null)
    } catch (e) { setError(`Backend unreachable: ${e.message}`) }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  // poll while a batch is running
  useEffect(() => {
    const tick = async () => {
      try {
        const s = await api.status()
        setRunState(s)
        if (s.running) { await refresh() } else if (timer.current) { clearInterval(timer.current); timer.current = null; await refresh() }
      } catch { /* ignore */ }
    }
    tick()
    return () => timer.current && clearInterval(timer.current)
  }, [refresh])

  const startPolling = () => {
    if (timer.current) return
    timer.current = setInterval(async () => {
      const s = await api.status().catch(() => null)
      if (!s) return
      setRunState(s)
      await refresh()
      if (!s.running) { clearInterval(timer.current); timer.current = null }
    }, 800)
  }

  const run = async () => {
    try { await api.runBatch(); setRunState({ running: true, done: 0, total: metrics?.total_payments }); startPolling() } catch (e) { setError(e.message) }
  }
  const reset = async () => { await api.reset(); refresh() }

  const openPayment = (id) => { setPaymentId(id); setView('payment') }
  const openAudit = (id) => { setAuditId(id || ''); setView('audit') }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="logo">R</div>
          <div>
            <h1>RecoverAI</h1>
            <p>Autonomous Revenue Recovery Agent</p>
          </div>
        </div>
        <nav>
          <button className={view === 'overview' ? 'active' : ''} onClick={() => setView('overview')}>Overview</button>
          <button className={view === 'payment' ? 'active' : ''} onClick={() => paymentId ? setView('payment') : openPayment('P0042')}>Agent Decision</button>
          <button className={view === 'audit' ? 'active' : ''} onClick={() => setView('audit')}>Audit Trail</button>
        </nav>
      </header>

      {error && <div className="banner bad" style={{ marginBottom: 16 }}>{error}</div>}

      {view === 'overview' && (
        <Dashboard metrics={metrics} health={health} running={!!runState?.running} runState={runState} onRun={run} onReset={reset} onOpen={openPayment} />
      )}
      {view === 'payment' && paymentId && (
        <PaymentDetails paymentId={paymentId} onBack={() => setView('overview')} onAudit={openAudit} onChanged={refresh} />
      )}
      {view === 'audit' && (
        <AuditTrail paymentId={auditId} onPick={setAuditId} onOpenPayment={openPayment} />
      )}

      <div className="footer-note">
        The LLM recommends actions — it never has unrestricted access to money movement. Every action passes a deterministic policy gate first.
        {' '}Demo cases: <a href="#" onClick={(e) => { e.preventDefault(); openPayment('P0042') }}>P0042 retry</a> · <a href="#" onClick={(e) => { e.preventDefault(); openPayment('P0003') }}>P0003 payment link</a> · <a href="#" onClick={(e) => { e.preventDefault(); openPayment('P0099') }}>P0099 escalation</a> · <a href="#" onClick={(e) => { e.preventDefault(); openPayment('P0117') }}>P0117 failed retry</a> · <a href="#" onClick={(e) => { e.preventDefault(); openPayment('P0210') }}>P0210 stale event</a>
      </div>
    </div>
  )
}
