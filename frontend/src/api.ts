const BASE = '/api'

function authHeaders(): Record<string, string> {
  const t = localStorage.getItem('access_token')
  return t ? { Authorization: `Bearer ${t}` } : {}
}

async function req<T>(method: string, path: string, body?: any): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401) {
    localStorage.removeItem('access_token')
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail))
  }
  return res.json()
}

export const api = {
  login: (email: string, password: string) =>
    req<{ access_token: string; role: string; tenant_id: string | null; user_id: string }>('POST', '/auth/login', { email, password }),
  me: () => req<{ user_id: string; role: string; tenant_id: string | null; email: string }>('GET', '/auth/me'),
  listBrokers: () => req<any[]>('GET', '/brokers'),
  listMasters: () => req<any[]>('GET', '/masters'),
  createMaster: (b: any) => req('POST', '/masters', b),
  listStrategies: () => req<any[]>('GET', '/strategies'),
  createStrategy: (s: any) => req('POST', '/strategies', s),
  listInvestors: () => req<any[]>('GET', '/investors'),
  createInvestor: (b: any) => req('POST', '/investors', b),
  listSubscriptions: () => req<any[]>('GET', '/subscriptions'),
  subscribe: (s: any) => req('POST', '/subscriptions', s),
  simulatePnl: (master_id: string, pnl: string) =>
    req('POST', `/simulate-pnl?master_id=${master_id}&pnl=${pnl}`),
  executeRollover: (b: any) => req<any>('POST', '/rollovers', b),
  listRollovers: (master_id: string) => req<any[]>('GET', `/masters/${master_id}/rollovers`),
  getRollover: (id: string) => req<any>('GET', `/rollovers/${id}`),
  getMerkleRoot: (rollover_id: string) => req<any>('GET', `/rollovers/${rollover_id}/merkle-root`),
  getProof: (rollover_id: string, subscription_id: string) =>
    req<any>('GET', `/rollovers/${rollover_id}/proofs/${subscription_id}`),
  getStatement: (rollover_id: string, subscription_id: string) =>
    req<any>('GET', `/rollovers/${rollover_id}/statement/${subscription_id}`),
  verifyAudit: () => req<any>('GET', '/audit/verify'),
  // M2
  mamSplit: (b: any) => req<any>('POST', '/mam/split', b),
  listCopySubscriptions: () => req<any[]>('GET', '/copy/subscriptions'),
  copySubscribe: (b: any) => req('POST', '/copy/subscriptions', b),
  copyControl: (b: any) => req<any>('POST', '/copy/control', b),
  openCopyTrade: (b: any) => req<any>('POST', '/copy/trades', b),
  listCopyTrades: () => req<any[]>('GET', '/copy/trades'),
  listSagas: () => req<any[]>('GET', '/sagas'),
  getSaga: (saga_id: string) => req<any>('GET', `/sagas/${saga_id}`),
  recoverSaga: (saga_id: string) => req<any>('POST', `/sagas/${saga_id}/recover`),
  // M3
  solveAllocation: (b: any) => req<any>('POST', '/allocation/solve', b),
  listAllocationProblems: () => req<any[]>('GET', '/allocation/problems'),
  listAllocationAlerts: () => req<any[]>('GET', '/allocation/alerts'),
  acknowledgeAlert: (id: string) => req<any>('POST', `/allocation/alerts/${id}/acknowledge`),
  predictLatency: (b: any) => req<any>('POST', '/latency/predict', b),
  observeLatency: (b: any) => req<any>('POST', '/latency/observe', b),
  getLatencyProfile: (destination: string, symbol?: string) =>
    req<any>('GET', `/latency/profiles/${destination}${symbol ? `?symbol=${symbol}` : ''}`),
  getCalibration: (destination: string, symbol?: string) =>
    req<any>('GET', `/latency/calibration?destination=${destination}${symbol ? `&symbol=${symbol}` : ''}`),
  drainOutbox: (limit: number) => req<any>('POST', `/outbox/drain?limit=${limit}`),
  outboxStats: () => req<any>('GET', '/outbox/stats'),
  // M5
  listAdapters: () => req<any[]>('GET', '/adapters'),
  getAdapter: (type: string) => req<any>('GET', `/adapters/${type}`),
  testConnect: (type: string) => req<any>('POST', `/adapters/${type}/test-connect`),
  // Public market data (no auth required)
  platformStats: () => req<any>('GET', '/public/stats'),
  topAccounts: (limit: number = 10, sort_by: string = 'return_pct') =>
    req<any[]>('GET', `/public/top-accounts?limit=${limit}&sort_by=${sort_by}`),
  publicManagers: (limit: number = 20) => req<any[]>('GET', `/public/managers?limit=${limit}`),
  publicStrategies: () => req<any[]>('GET', '/public/strategies'),
}
