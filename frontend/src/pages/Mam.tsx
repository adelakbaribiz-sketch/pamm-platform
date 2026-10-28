import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'

const SAMPLE_INVESTORS: Record<string, any> = {
  equity_ratio: [
    { investor_id: 'A', subscription_id: '', investor_account_id: '', equity: '1000', min_allocation: '0', max_allocation: '1000', peak_capital: '1000', drawdown_limit_pct: '1.0' },
    { investor_id: 'B', subscription_id: '', investor_account_id: '', equity: '3000', min_allocation: '0', max_allocation: '10000', peak_capital: '10000', drawdown_limit_pct: '1.0' },
  ],
  balance_ratio: [
    { investor_id: 'A', subscription_id: '', investor_account_id: '', balance: '500', min_allocation: '0', max_allocation: '500', peak_capital: '500', drawdown_limit_pct: '1.0' },
    { investor_id: 'B', subscription_id: '', investor_account_id: '', balance: '1500', min_allocation: '0', max_allocation: '10000', peak_capital: '10000', drawdown_limit_pct: '1.0' },
  ],
  fixed_lot_mult: [
    { investor_id: 'A', subscription_id: '', investor_account_id: '', lot_multiplier: '0.5' },
    { investor_id: 'B', subscription_id: '', investor_account_id: '', lot_multiplier: '2.0' },
  ],
  percentage: [
    { investor_id: 'A', subscription_id: '', investor_account_id: '', percentage: '0.25' },
    { investor_id: 'B', subscription_id: '', investor_account_id: '', percentage: '0.75' },
  ],
}

export default function Mam() {
  const qc = useQueryClient()
  const { data: masters } = useQuery({ queryKey: ['masters'], queryFn: api.listMasters })
  const { data: subs } = useQuery({ queryKey: ['subs'], queryFn: api.listSubscriptions })
  const { data: sagas } = useQuery({ queryKey: ['sagas'], queryFn: api.listSagas })

  const [result, setResult] = useState<any>(null)
  const [err, setErr] = useState('')
  const [jsonError, setJsonError] = useState('')
  const [form, setForm] = useState({
    master_account_id: '',
    symbol: 'EURUSD',
    side: 'buy',
    master_lots: '4',
    method: 'equity_ratio',
    lot_step: '0.01',
    price: '1.10',
    idempotency_key: '',
    investors: JSON.stringify(SAMPLE_INVESTORS.equity_ratio, null, 2),
  })

  function validateJson(s: string): boolean {
    try { JSON.parse(s); setJsonError(''); return true }
    catch (e: any) { setJsonError(e.message); return false }
  }

  const split = useMutation({
    mutationFn: () => {
      if (!validateJson(form.investors)) throw new Error('Investors JSON is invalid')
      const investors = JSON.parse(form.investors)
      // Auto-populate subscription_id + investor_account_id if user provided only investor_id
      // and an active subscription under this master exists.
      const masterSubs = (subs || []).filter(s => s.master_account_id === form.master_account_id && s.status === 'active')
      const enriched = investors.map((inv: any, i: number) => {
        if ((!inv.subscription_id || !inv.investor_account_id) && masterSubs[i]) {
          return { ...inv, subscription_id: masterSubs[i].id, investor_account_id: masterSubs[i].investor_account_id }
        }
        return inv
      })
      const body: any = {
        master_account_id: form.master_account_id,
        symbol: form.symbol, side: form.side, master_lots: form.master_lots,
        method: form.method, lot_step: form.lot_step,
        idempotency_key: form.idempotency_key || crypto.randomUUID(),
        price: form.price, investors: enriched,
      }
      return api.mamSplit(body)
    },
    onSuccess: (r) => { setResult(r); setErr(''); qc.invalidateQueries({ queryKey: ['sagas'] }) },
    onError: (e: any) => setErr(e.message),
  })

  function loadSample(method: string) {
    const sample = SAMPLE_INVESTORS[method] || SAMPLE_INVESTORS.equity_ratio
    setForm({ ...form, method, investors: JSON.stringify(sample, null, 2) })
    setJsonError('')
  }

  function autoFillFromSubs() {
    const masterSubs = (subs || []).filter(s => s.master_account_id === form.master_account_id && s.status === 'active')
    if (masterSubs.length === 0) {
      setErr('No active subscriptions under this master. Create PAMM/MAM subscriptions first.')
      return
    }
    const invs = masterSubs.map(s => ({
      investor_id: s.investor_login || s.id.slice(0, 8),
      subscription_id: s.id,
      investor_account_id: s.investor_account_id,
      equity: s.contributed_capital,
      min_allocation: '0',
      max_allocation: str_max(s.contributed_capital, '1000000'),
      peak_capital: s.contributed_capital,
      drawdown_limit_pct: '1.0',
    }))
    setForm({ ...form, investors: JSON.stringify(invs, null, 2) })
    setErr('')
  }

  function str_max(a: string, b: string): string {
    const da = Number(a), db = Number(b)
    return String(da > db ? da : db)
  }

  // MAM saga (most recent mam_batch)
  const mamSagas = (sagas || []).filter(s => s.kind === 'mam_batch').slice(0, 5)

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">MAM Split (Master-Order Allocation)</h1>

      <div className="card p-4 mb-6">
        <h2 className="font-semibold mb-3">Configuration</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-3">
          <div><label className="label">Master Account</label>
            <select className="input" value={form.master_account_id} onChange={e => setForm({...form, master_account_id: e.target.value})}>
              <option value="">—</option>
              {(masters || []).map(m => <option key={m.id} value={m.id}>{m.login}</option>)}
            </select>
          </div>
          <div><label className="label">Symbol</label><input className="input" value={form.symbol} onChange={e => setForm({...form, symbol: e.target.value})} /></div>
          <div><label className="label">Side</label>
            <select className="input" value={form.side} onChange={e => setForm({...form, side: e.target.value})}>
              <option value="buy">buy</option>
              <option value="sell">sell</option>
            </select>
          </div>
          <div><label className="label">Master Lots</label><input className="input" value={form.master_lots} onChange={e => setForm({...form, master_lots: e.target.value})} /></div>
          <div><label className="label">Method</label>
            <select className="input" value={form.method} onChange={e => loadSample(e.target.value)}>
              <option value="equity_ratio">equity_ratio</option>
              <option value="balance_ratio">balance_ratio</option>
              <option value="fixed_lot_mult">fixed_lot_mult</option>
              <option value="percentage">percentage</option>
            </select>
          </div>
          <div><label className="label">Lot Step</label><input className="input" value={form.lot_step} onChange={e => setForm({...form, lot_step: e.target.value})} /></div>
          <div><label className="label">Price</label><input className="input" value={form.price} onChange={e => setForm({...form, price: e.target.value})} /></div>
          <div><label className="label">Idempotency Key (auto)</label><input className="input" value={form.idempotency_key} onChange={e => setForm({...form, idempotency_key: e.target.value})} placeholder="auto-generated" /></div>
        </div>

        <div className="flex justify-between items-center mb-2">
          <label className="label !mb-0">Investors (JSON array)</label>
          <div className="flex gap-2">
            <button className="btn-ghost text-xs" onClick={() => loadSample(form.method)}>Load sample</button>
            <button className="btn-ghost text-xs" onClick={autoFillFromSubs} disabled={!form.master_account_id}>Auto-fill from active subs</button>
          </div>
        </div>
        <textarea
          className={`input font-mono text-xs ${jsonError ? 'border-red-500' : ''}`}
          rows={10}
          value={form.investors}
          onChange={e => { setForm({...form, investors: e.target.value}); validateJson(e.target.value) }}
        />
        {jsonError && <div className="text-red-500 text-xs mt-1">JSON error: {jsonError}</div>}

        <div className="mt-3 flex items-center gap-3">
          <button className="btn-primary" disabled={!form.master_account_id || split.isPending || !!jsonError} onClick={() => split.mutate()}>
            {split.isPending ? 'Splitting…' : 'Execute MAM Split'}
          </button>
          <span className="text-xs text-slate-500">
            A settlement saga is created for each split. Compensation logs irreversible broker trades as remediation (not fake reversal).
          </span>
        </div>
        {err && <div className="text-red-500 text-xs mt-3">{err}</div>}
      </div>

      {result && (
        <div className="card p-4 mb-6">
          <h2 className="font-semibold mb-3">Split Result</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4 text-sm">
            <div><div className="text-xs text-slate-500">Master Order</div><div className="font-mono text-xs break-all">{result.master_order_id}</div></div>
            <div><div className="text-xs text-slate-500">Saga</div><div className="font-mono text-xs break-all">{result.saga_id}</div></div>
            <div><div className="text-xs text-slate-500">Reconciled</div>
              <div className="font-bold">
                {result.reconciled ? <span className="text-green-600">YES ✓</span> : <span className="text-red-600">NO ✗</span>}
              </div>
            </div>
          </div>
          {result.children && result.children.length > 0 && (
            <table className="w-full text-sm">
              <thead className="text-left text-slate-500 border-b border-slate-200 dark:border-slate-700">
                <tr>
                  <th className="py-2">Subscription</th>
                  <th>Investor</th>
                  <th>Requested</th>
                  <th>Allocated</th>
                  <th>Residual</th>
                  <th>Status</th>
                  <th>Fill Price</th>
                </tr>
              </thead>
              <tbody>
                {result.children.map((c: any) => (
                  <tr key={c.subscription_id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-2 font-mono text-xs">{c.subscription_id.slice(0, 8)}</td>
                    <td className="font-mono text-xs">{c.investor_account_id.slice(0, 8)}</td>
                    <td>{c.requested_lots}</td>
                    <td className="font-medium">{c.allocated_lots}</td>
                    <td className="text-amber-700 dark:text-amber-300">{c.residual_lots}</td>
                    <td>
                      <span className={
                        c.status === 'filled' ? 'tag-ok' :
                        c.status === 'rejected' ? 'tag-danger' : 'tag-mock'
                      }>{c.status}</span>
                      {c.reject_reason && <div className="text-xs text-red-500">{c.reject_reason}</div>}
                    </td>
                    <td>{c.fill_price || '—'}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="border-t-2 border-slate-300 dark:border-slate-600 font-medium">
                <tr>
                  <td className="py-2" colSpan={2}>Totals:</td>
                  <td>{result.children.reduce((s: number, c: any) => s + Number(c.requested_lots), 0).toFixed(2)}</td>
                  <td>{result.children.reduce((s: number, c: any) => s + Number(c.allocated_lots), 0).toFixed(2)}</td>
                  <td>{result.children.reduce((s: number, c: any) => s + Number(c.residual_lots), 0).toFixed(2)}</td>
                  <td colSpan={2}></td>
                </tr>
              </tfoot>
            </table>
          )}
          <div className="mt-3 text-xs text-slate-500">
            <strong>Residual lots</strong> are the lot-step increments distributed from the master order total
            to investors with the largest fractional remainders, ensuring cent-exact reconciliation.
          </div>
        </div>
      )}

      <div className="card p-4">
        <h2 className="font-semibold mb-3">Recent MAM Sagas</h2>
        <table className="w-full text-sm">
          <thead className="text-left text-slate-500 border-b border-slate-200 dark:border-slate-700">
            <tr>
              <th className="py-2">Saga ID</th>
              <th>Status</th>
              <th>Completed Steps</th>
              <th>Failed Step</th>
              <th>Compensations</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {mamSagas.map(s => (
              <tr key={s.saga_id} className="border-t border-slate-100 dark:border-slate-800">
                <td className="py-2 font-mono text-xs">{s.saga_id.slice(0, 8)}</td>
                <td><span className={
                  s.status === 'completed' ? 'tag-ok' :
                  s.status === 'failed' ? 'tag-danger' :
                  s.status === 'compensating' ? 'tag-warn' : 'tag-mock'
                }>{s.status}</span></td>
                <td className="text-xs">{(s.completed_steps || []).length}</td>
                <td className="text-xs text-red-600">{s.failed_step || '—'}</td>
                <td className="text-xs text-amber-600">{(s.compensation_log || []).length}</td>
                <td className="text-xs">{new Date(s.created_at).toLocaleString()}</td>
              </tr>
            ))}
            {mamSagas.length === 0 && (
              <tr><td colSpan={6} className="py-4 text-center text-slate-500">No MAM sagas yet — execute a split above.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
