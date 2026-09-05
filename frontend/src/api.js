const BASE = import.meta.env.VITE_API_BASE || ''
const j = async (r) => {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json()
}

export const api = {
  health: () => fetch(`${BASE}/api/health`).then(j),
  policy: () => fetch(`${BASE}/api/policy`).then(j),
  metrics: () => fetch(`${BASE}/api/metrics`).then(j),
  payments: (status) => fetch(`${BASE}/api/payments${status ? `?status=${status}` : ''}`).then(j),
  payment: (id) => fetch(`${BASE}/api/payments/${id}`).then(j),
  cases: (status) => fetch(`${BASE}/api/cases${status ? `?status=${status}` : ''}`).then(j),
  audit: (id, limit = 300) => fetch(`${BASE}/api/audit?${id ? `payment_id=${id}&` : ''}limit=${limit}`).then(j),
  runBatch: (opts = {}) => {
    const q = new URLSearchParams()
    if (opts.limit) q.set('limit', opts.limit)
    if (opts.use_llm !== undefined) q.set('use_llm', opts.use_llm)
    return fetch(`${BASE}/api/agent/recover?${q}`, { method: 'POST' }).then(j)
  },
  runOne: (id) => fetch(`${BASE}/api/agent/recover/${id}`, { method: 'POST' }).then(j),
  status: () => fetch(`${BASE}/api/agent/status`).then(j),
  reset: () => fetch(`${BASE}/api/reset`, { method: 'POST' }).then(j),
}

export const inr = (n) => {
  if (n == null) return '—'
  const abs = Math.abs(n)
  if (abs >= 1e7) return `₹${(n / 1e7).toFixed(2)}Cr`
  if (abs >= 1e5) return `₹${(n / 1e5).toFixed(2)}L`
  if (abs >= 1e3) return `₹${(n / 1e3).toFixed(1)}K`
  return `₹${Math.round(n).toLocaleString('en-IN')}`
}
export const inrFull = (n) => `₹${Math.round(n ?? 0).toLocaleString('en-IN')}`
export const pct = (n, d = 1) => `${(n ?? 0).toFixed(d)}%`
export const title = (s) => (s || '').replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase())
