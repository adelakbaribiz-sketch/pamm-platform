import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'

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

export default function Investors() {
  const qc = useQueryClient()
  const { data: investors } = useQuery({ queryKey: ['investors'], queryFn: api.listInvestors })
  const { data: subs } = useQuery({ queryKey: ['subs'], queryFn: api.listSubscriptions })
  const { data: brokers } = useQuery({ queryKey: ['brokers'], queryFn: api.listBrokers })
  const { data: strategies } = useQuery({ queryKey: ['strategies'], queryFn: api.listStrategies })
  const [showInv, setShowInv] = useState(false)
  const [showSub, setShowSub] = useState(false)
  const [invForm, setInvForm] = useState({ broker_id: '', login: '', currency: 'USD' })
  const [subForm, setSubForm] = useState({ strategy_id: '', investor_account_id: '', capital: '1000' })

  const createInv = useMutation({ mutationFn: () => api.createInvestor(invForm), onSuccess: () => { qc.invalidateQueries({ queryKey: ['investors'] }); setShowInv(false) } })
  const subscribe = useMutation({ mutationFn: () => api.subscribe(subForm), onSuccess: () => { qc.invalidateQueries({ queryKey: ['subs', 'masters'] }); setShowSub(false) } })

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">Investors & Subscriptions</h1>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={() => { setInvForm({...invForm, broker_id: brokers?.[0]?.id || ''}); setShowInv(true) }}>New Investor</button>
          <button className="btn-primary" onClick={() => setShowSub(true)}>Subscribe</button>
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-4">
          <h2 className="font-semibold mb-3">Investor Accounts</h2>
          <table className="w-full text-sm">
            <thead className="text-left text-slate-500"><tr><th className="py-2">Login</th><th>Currency</th><th>Status</th></tr></thead>
            <tbody>
              {(investors || []).map(i => (
                <tr key={i.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-2 font-mono">{i.login}</td><td>{i.currency}</td>
                  <td><span className="tag-ok">{i.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card p-4">
          <h2 className="font-semibold mb-3">Subscriptions</h2>
          <table className="w-full text-sm">
            <thead className="text-left text-slate-500"><tr><th className="py-2">Investor</th><th>Capital</th><th>Units</th><th>NAV</th><th>GAV</th><th>P&L</th></tr></thead>
            <tbody>
              {(subs || []).map(s => (
                <tr key={s.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-2 font-mono">{s.investor_login}</td>
                  <td>${Number(s.contributed_capital).toFixed(2)}</td>
                  <td>{Number(s.units).toFixed(4)}</td>
                  <td>${Number(s.current_nav).toFixed(4)}</td>
                  <td>${Number(s.current_gav).toFixed(2)}</td>
                  <td className={Number(s.unrealized_pnl) >= 0 ? 'text-green-600' : 'text-red-600'}>${Number(s.unrealized_pnl).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {showInv && (
        <Modal title="New Investor Account" onClose={() => setShowInv(false)}>
          <div className="space-y-3">
            <div><label className="label">Broker</label>
              <select className="input" value={invForm.broker_id} onChange={e => setInvForm({...invForm, broker_id: e.target.value})}>
                <option value="">—</option>
                {(brokers || []).map(b => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </div>
            <div><label className="label">Login</label><input className="input" value={invForm.login} onChange={e => setInvForm({...invForm, login: e.target.value})} /></div>
            <div><label className="label">Currency</label><input className="input" value={invForm.currency} onChange={e => setInvForm({...invForm, currency: e.target.value})} /></div>
            <button className="btn-primary w-full" onClick={() => createInv.mutate()} disabled={createInv.isPending}>Create</button>
          </div>
        </Modal>
      )}
      {showSub && (
        <Modal title="Subscribe Investor to Strategy" onClose={() => setShowSub(false)}>
          <div className="space-y-3">
            <div><label className="label">Strategy</label>
              <select className="input" value={subForm.strategy_id} onChange={e => setSubForm({...subForm, strategy_id: e.target.value})}>
                <option value="">—</option>
                {(strategies || []).filter(s => s.kind !== 'copy').map(s => <option key={s.id} value={s.id}>{s.name} ({s.kind})</option>)}
              </select>
            </div>
            <div><label className="label">Investor Account</label>
              <select className="input" value={subForm.investor_account_id} onChange={e => setSubForm({...subForm, investor_account_id: e.target.value})}>
                <option value="">—</option>
                {(investors || []).map(i => <option key={i.id} value={i.id}>{i.login}</option>)}
              </select>
            </div>
            <div><label className="label">Capital</label><input className="input" value={subForm.capital} onChange={e => setSubForm({...subForm, capital: e.target.value})} /></div>
            <button className="btn-primary w-full" onClick={() => subscribe.mutate()} disabled={subscribe.isPending}>Subscribe</button>
          </div>
        </Modal>
      )}
    </div>
  )
}
