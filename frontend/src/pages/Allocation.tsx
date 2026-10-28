import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'
import { PageHeader } from '../components/ui'

export default function Allocation() {
  const qc = useQueryClient()
  const { data: masters } = useQuery({ queryKey: ['masters'], queryFn: api.listMasters })
  const { data: problems } = useQuery({ queryKey: ['alloc-problems'], queryFn: api.listAllocationProblems })
  const { data: alerts } = useQuery({ queryKey: ['alloc-alerts'], queryFn: api.listAllocationAlerts })
  const [result, setResult] = useState<any>(null)
  const [err, setErr] = useState('')
  const [form, setForm] = useState({
    master_account_id: '', objective: 'maximize_return', free_margin: '10000',
    investors: '[{"investor_id":"A","expected_return":"0.15","volatility":"0.05","min_allocation":"0","max_allocation":"10000","peak_capital":"10000","drawdown_limit_pct":"1.0"},{"investor_id":"B","expected_return":"0.10","volatility":"0.04","min_allocation":"0","max_allocation":"10000","peak_capital":"10000","drawdown_limit_pct":"1.0"}]',
  })
  const solve = useMutation({
    mutationFn: () => {
      const body: any = {
        master_account_id: form.master_account_id,
        objective: form.objective, free_margin: form.free_margin,
        investors: JSON.parse(form.investors),
      }
      return api.solveAllocation(body)
    },
    onSuccess: (r) => { setResult(r); setErr(''); qc.invalidateQueries({ queryKey: ['alloc-problems', 'alloc-alerts'] }) },
    onError: (e: any) => setErr(e.message),
  })
  const ack = useMutation({ mutationFn: (id: string) => api.acknowledgeAlert(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alloc-alerts'] }) })

  return (
    <div>
      <PageHeader eyebrow="Allocation" title="Risk-constrained allocation" subtitle="Linear-programming allocator that respects per-investor risk limits; breaches raise alerts for review." />
      <div className="card p-4 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
          <div><label className="label">Master Account</label>
            <select className="input" value={form.master_account_id} onChange={e => setForm({...form, master_account_id: e.target.value})}>
              <option value="">—</option>
              {(masters || []).map(m => <option key={m.id} value={m.id}>{m.login}</option>)}
            </select>
          </div>
          <div><label className="label">Objective</label>
            <select className="input" value={form.objective} onChange={e => setForm({...form, objective: e.target.value})}>
              <option value="maximize_return">maximize_return</option>
              <option value="minimize_risk">minimize_risk</option>
              <option value="balanced">balanced</option>
            </select>
          </div>
          <div><label className="label">Free Margin</label><input className="input" value={form.free_margin} onChange={e => setForm({...form, free_margin: e.target.value})} /></div>
        </div>
        <div><label className="label">Investors (JSON)</label>
          <textarea className="input font-mono text-xs" rows={8} value={form.investors} onChange={e => setForm({...form, investors: e.target.value})} />
        </div>
        <button className="btn-primary mt-3" disabled={!form.master_account_id || solve.isPending} onClick={() => solve.mutate()}>
          {solve.isPending ? 'Solving LP…' : 'Solve Allocation'}
        </button>
        {err && <div className="text-red-500 text-xs mt-3">{err}</div>}
      </div>
      {result && (
        <div className="card p-4 mb-6">
          <h2 className="font-semibold mb-3">Solver Result</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4 text-sm">
            <div><div className="text-xs text-slate-500">Status</div>
              <div className="font-bold">
                <span className={result.status === 'optimal' ? 'tag-ok' : result.status === 'infeasible' ? 'tag-danger' : 'tag-warn'}>{result.status}</span>
              </div>
            </div>
            <div><div className="text-xs text-slate-500">Objective Value</div><div className="font-bold">{result.objective_value || '—'}</div></div>
            <div><div className="text-xs text-slate-500">Frozen</div><div className="font-bold">{result.frozen ? 'YES' : 'NO'}</div></div>
            <div><div className="text-xs text-slate-500">Alert Emitted</div><div className="font-bold">{result.alert_emitted ? 'YES' : 'NO'}</div></div>
          </div>
          {result.infeasibility_reason && <div className="text-red-600 text-xs mb-3">Reason: {result.infeasibility_reason}</div>}
          {Object.keys(result.allocations).length > 0 && (
            <table className="w-full text-sm">
              <thead className="text-left text-slate-500"><tr><th className="py-2">Investor</th><th>Allocation</th></tr></thead>
              <tbody>
                {Object.entries(result.allocations).map(([id, amt]) => (
                  <tr key={id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-2 font-mono">{id}</td>
                    <td>${String(amt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-4">
          <h2 className="font-semibold mb-3">Recent Problems</h2>
          <table className="w-full text-sm">
            <thead className="text-left text-slate-500"><tr><th className="py-2">Problem</th><th>Objective</th><th>Status</th><th>Frozen</th></tr></thead>
            <tbody>
              {(problems || []).map(p => (
                <tr key={p.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-2 font-mono text-xs">{p.id.slice(0, 8)}</td>
                  <td>{p.objective}</td>
                  <td><span className={p.status === 'optimal' ? 'tag-ok' : 'tag-danger'}>{p.status}</span></td>
                  <td>{p.frozen ? 'YES' : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card p-4">
          <h2 className="font-semibold mb-3">Infeasibility Alerts</h2>
          <table className="w-full text-sm">
            <thead className="text-left text-slate-500"><tr><th className="py-2">Kind</th><th>Acknowledged</th><th>Created</th><th></th></tr></thead>
            <tbody>
              {(alerts || []).map(a => (
                <tr key={a.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-2"><span className="tag-danger">{a.kind}</span></td>
                  <td>{a.acknowledged ? 'YES' : 'NO'}</td>
                  <td className="text-xs">{new Date(a.created_at).toLocaleString()}</td>
                  <td>{!a.acknowledged && <button className="btn-ghost text-xs" onClick={() => ack.mutate(a.id)}>Ack</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
