import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'

export default function MasterAccounts() {
  const qc = useQueryClient()
  const { data: brokers } = useQuery({ queryKey: ['brokers'], queryFn: api.listBrokers })
  const { data: masters } = useQuery({ queryKey: ['masters'], queryFn: api.listMasters })
  const { data: strategies } = useQuery({ queryKey: ['strategies'], queryFn: api.listStrategies })
  const [showMaster, setShowMaster] = useState(false)
  const [showStrat, setShowStrat] = useState(false)
  const [pnlModal, setPnlModal] = useState<string | null>(null)
  const [mForm, setMForm] = useState({ broker_id: '', login: '', currency: 'USD',
    base_nav: '100', performance_fee_rate: '0.2', allocation_method: 'euro_days' })
  const [sForm, setSForm] = useState({ master_account_id: '', name: '', description: '', kind: 'pamm' })
  const [pnl, setPnl] = useState('')

  const createM = useMutation({ mutationFn: () => api.createMaster(mForm), onSuccess: () => { qc.invalidateQueries({ queryKey: ['masters'] }); setShowMaster(false) } })
  const createS = useMutation({ mutationFn: () => api.createStrategy(sForm), onSuccess: () => { qc.invalidateQueries({ queryKey: ['strategies'] }); setShowStrat(false) } })
  const simPnl = useMutation({ mutationFn: () => api.simulatePnl(pnlModal!, pnl), onSuccess: () => { qc.invalidateQueries({ queryKey: ['masters'] }); setPnlModal(null); setPnl('') } })

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Master Accounts & Strategies</h1>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={() => { setMForm({...mForm, broker_id: brokers?.[0]?.id || ''}); setShowMaster(true) }}>New Master</button>
          <button className="btn-primary" onClick={() => { setSForm({...sForm, master_account_id: masters?.[0]?.id || ''}); setShowStrat(true) }}>New Strategy</button>
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-4">
          <h2 className="font-semibold mb-3">Master Accounts</h2>
          <table className="w-full text-sm">
            <thead className="text-left text-slate-500"><tr><th className="py-2">Login</th><th>Method</th><th>Equity</th><th>NAV</th><th></th></tr></thead>
            <tbody>
              {(masters || []).map(m => (
                <tr key={m.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-2 font-mono">{m.login}</td>
                  <td>{m.allocation_method}</td>
                  <td>${Number(m.equity).toFixed(2)}</td>
                  <td>${Number(m.nav).toFixed(4)}</td>
                  <td><button className="btn-ghost text-xs" onClick={() => setPnlModal(m.id)}>Simulate P&L</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card p-4">
          <h2 className="font-semibold mb-3">Strategies</h2>
          <ul className="space-y-2">
            {(strategies || []).map(s => (
              <li key={s.id} className="border border-slate-200 dark:border-slate-700 rounded p-3">
                <div className="font-medium">{s.name} <span className={`tag ml-2 ${s.kind === 'pamm' ? 'tag-ok' : s.kind === 'mam' ? 'tag-warn' : 'tag-mock'}`}>{s.kind}</span></div>
                <div className="text-xs text-slate-500">{s.description}</div>
              </li>
            ))}
          </ul>
        </div>
      </div>
      {showMaster && (
        <Modal title="New Master Account" onClose={() => setShowMaster(false)}>
          <div className="space-y-3">
            <div><label className="label">Broker</label>
              <select className="input" value={mForm.broker_id} onChange={e => setMForm({...mForm, broker_id: e.target.value})}>
                <option value="">— select —</option>
                {(brokers || []).map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </div>
            <div><label className="label">Login</label><input className="input" value={mForm.login} onChange={e => setMForm({...mForm, login: e.target.value})} /></div>
            <div className="grid grid-cols-2 gap-2">
              <div><label className="label">Currency</label><input className="input" value={mForm.currency} onChange={e => setMForm({...mForm, currency: e.target.value})} /></div>
              <div><label className="label">Base NAV</label><input className="input" value={mForm.base_nav} onChange={e => setMForm({...mForm, base_nav: e.target.value})} /></div>
              <div><label className="label">Perf Fee Rate</label><input className="input" value={mForm.performance_fee_rate} onChange={e => setMForm({...mForm, performance_fee_rate: e.target.value})} /></div>
              <div><label className="label">Method</label>
                <select className="input" value={mForm.allocation_method} onChange={e => setMForm({...mForm, allocation_method: e.target.value})}>
                  <option value="euro_days">euro_days</option>
                  <option value="start_capital">start_capital</option>
                  <option value="end_capital">end_capital</option>
                </select>
              </div>
            </div>
            <button className="btn-primary w-full" onClick={() => createM.mutate()} disabled={createM.isPending}>Create</button>
          </div>
        </Modal>
      )}
      {showStrat && (
        <Modal title="New Strategy" onClose={() => setShowStrat(false)}>
          <div className="space-y-3">
            <div><label className="label">Master Account</label>
              <select className="input" value={sForm.master_account_id} onChange={e => setSForm({...sForm, master_account_id: e.target.value})}>
                <option value="">— select —</option>
                {(masters || []).map(m => <option key={m.id} value={m.id}>{m.login}</option>)}
              </select>
            </div>
            <div><label className="label">Kind</label>
              <select className="input" value={sForm.kind} onChange={e => setSForm({...sForm, kind: e.target.value})}>
                <option value="pamm">pamm</option>
                <option value="mam">mam</option>
                <option value="copy">copy</option>
              </select>
            </div>
            <div><label className="label">Name</label><input className="input" value={sForm.name} onChange={e => setSForm({...sForm, name: e.target.value})} /></div>
            <div><label className="label">Description</label><textarea className="input" rows={3} value={sForm.description} onChange={e => setSForm({...sForm, description: e.target.value})} /></div>
            <button className="btn-primary w-full" onClick={() => createS.mutate()} disabled={createS.isPending}>Create</button>
          </div>
        </Modal>
      )}
      {pnlModal && (
        <Modal title={`Simulate P&L`} onClose={() => setPnlModal(null)}>
          <div className="space-y-3">
            <div className="tag-mock">Simulated broker — no real orders placed.</div>
            <div><label className="label">P&L amount</label><input className="input" value={pnl} onChange={e => setPnl(e.target.value)} placeholder="e.g. 500 or -200" /></div>
            <button className="btn-primary w-full" onClick={() => simPnl.mutate()} disabled={simPnl.isPending}>Apply</button>
          </div>
        </Modal>
      )}
    </div>
  )
}

function Modal({ title, children, onClose }: any) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="card p-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4"><h3 className="font-semibold">{title}</h3><button onClick={onClose} className="text-slate-400">✕</button></div>
        {children}
      </div>
    </div>
  )
}
