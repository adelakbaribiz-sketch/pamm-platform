import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'

export default function Rollover() {
  const qc = useQueryClient()
  const { data: masters } = useQuery({ queryKey: ['masters'], queryFn: api.listMasters })
  const [masterId, setMasterId] = useState('')
  const [method, setMethod] = useState('euro_days')
  const [periodDays, setPeriodDays] = useState('1')
  const [result, setResult] = useState<any>(null)
  const [err, setErr] = useState('')
  const execute = useMutation({
    mutationFn: () => api.executeRollover({ master_account_id: masterId, method, idempotency_key: crypto.randomUUID(), period_days: Number(periodDays) }),
    onSuccess: (r) => { setResult(r); setErr(''); qc.invalidateQueries({ queryKey: ['masters'] }); qc.invalidateQueries({ queryKey: ['subs'] }) },
    onError: (e: any) => setErr(e.message),
  })
  const { data: rollovers } = useQuery({ queryKey: ['rollovers', masterId], queryFn: () => api.listRollovers(masterId), enabled: !!masterId })
  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Rollover Processing</h1>
      <div className="card p-4 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div><label className="label">Master Account</label>
            <select className="input" value={masterId} onChange={e => setMasterId(e.target.value)}>
              <option value="">—</option>
              {(masters || []).map(m => <option key={m.id} value={m.id}>{m.login}</option>)}
            </select>
          </div>
          <div><label className="label">Method</label>
            <select className="input" value={method} onChange={e => setMethod(e.target.value)}>
              <option value="euro_days">euro_days</option>
              <option value="start_capital">start_capital</option>
              <option value="end_capital">end_capital</option>
            </select>
          </div>
          <div><label className="label">Period Days</label><input className="input" value={periodDays} onChange={e => setPeriodDays(e.target.value)} /></div>
          <div className="flex items-end"><button className="btn-primary w-full" disabled={!masterId || execute.isPending} onClick={() => execute.mutate()}>{execute.isPending ? 'Processing…' : 'Execute Rollover'}</button></div>
        </div>
        {err && <div className="text-red-500 text-xs mt-3">{err}</div>}
      </div>
      {result && (
        <div className="card p-4 mb-6">
          <h2 className="font-semibold mb-3">Rollover Result</h2>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4 text-sm">
            <Stat label="NAV Before" value={`$${Number(result.nav_before).toFixed(4)}`} />
            <Stat label="NAV After" value={`$${Number(result.nav_after).toFixed(4)}`} />
            <Stat label="Total Units" value={Number(result.total_units).toFixed(4)} />
            <Stat label="Total Fee" value={`$${Number(result.total_performance_fee).toFixed(2)}`} />
            <Stat label="Status" value={<span className="tag-ok">{result.status}</span>} />
          </div>
          <table className="w-full text-sm">
            <thead className="text-left text-slate-500"><tr><th className="py-2">Investor</th><th>Units</th><th>PnL Share</th><th>Fee</th><th>Units After</th></tr></thead>
            <tbody>
              {result.entries.map((e: any) => (
                <tr key={e.subscription_id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-2 font-mono">{e.investor_login}</td>
                  <td>{Number(e.units).toFixed(4)}</td>
                  <td>${Number(e.pnl_share).toFixed(2)}</td>
                  <td>${Number(e.performance_fee).toFixed(2)}</td>
                  <td>{Number(e.units_after).toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="card p-4">
        <h2 className="font-semibold mb-3">Rollover History</h2>
        <table className="w-full text-sm">
          <thead className="text-left text-slate-500"><tr><th className="py-2">ID</th><th>Method</th><th>NAV After</th><th>Total Fee</th><th>Period End</th></tr></thead>
          <tbody>
            {(rollovers || []).map(r => (
              <tr key={r.id} className="border-t border-slate-100 dark:border-slate-800">
                <td className="py-2 font-mono text-xs">{r.id.slice(0, 8)}</td>
                <td>{r.method}</td>
                <td>${Number(r.nav_after).toFixed(4)}</td>
                <td>${Number(r.total_performance_fee).toFixed(2)}</td>
                <td className="text-xs">{new Date(r.period_end).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
function Stat({ label, value }: any) {
  return <div><div className="text-xs text-slate-500 mb-1">{label}</div><div className="font-semibold">{value}</div></div>
}
