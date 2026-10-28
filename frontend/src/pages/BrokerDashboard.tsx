import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import { useAuth } from '../auth'

export default function BrokerDashboard() {
  const { session } = useAuth()
  const { data: masters } = useQuery({ queryKey: ['masters'], queryFn: api.listMasters })
  const { data: subs } = useQuery({ queryKey: ['subs'], queryFn: api.listSubscriptions })
  const { data: strats } = useQuery({ queryKey: ['strats'], queryFn: api.listStrategies })
  const { data: sagas } = useQuery({ queryKey: ['sagas'], queryFn: api.listSagas })
  const { data: alerts } = useQuery({ queryKey: ['alerts'], queryFn: api.listAllocationAlerts })
  const { data: outboxStats } = useQuery({ queryKey: ['outbox-stats'], queryFn: api.outboxStats })
  const { data: audit } = useQuery({ queryKey: ['audit'], queryFn: api.verifyAudit })

  const totalEquity = (masters || []).reduce((s, m) => s + Number(m.equity), 0)
  const pammCount = (strats || []).filter(s => s.kind === 'pamm').length
  const mamCount = (strats || []).filter(s => s.kind === 'mam').length
  const copyCount = (strats || []).filter(s => s.kind === 'copy').length

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Broker Dashboard (M3)</h1>
          <p className="text-sm text-slate-500">Tenant: {session?.tenant_id || 'super admin'} · Role: {session?.role}</p>
        </div>
        <span className="tag-mock">Simulated broker adapter</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className="stat"><div className="text-xs text-slate-500 mb-1">Master Accounts</div><div className="text-2xl font-bold">{masters?.length ?? 0}</div></div>
        <div className="stat"><div className="text-xs text-slate-500 mb-1">Total Equity</div><div className="text-2xl font-bold">${totalEquity.toFixed(2)}</div></div>
        <div className="stat"><div className="text-xs text-slate-500 mb-1">Active Subscriptions</div><div className="text-2xl font-bold">{(subs || []).filter(s => s.status === 'active').length}</div></div>
        <div className="stat"><div className="text-xs text-slate-500 mb-1">Allocation Alerts</div><div className="text-2xl font-bold text-red-600">{(alerts || []).filter(a => !a.acknowledged).length}</div></div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className="stat"><div className="text-xs text-slate-500 mb-1">PAMM Strategies</div><div className="text-2xl font-bold">{pammCount}</div></div>
        <div className="stat"><div className="text-xs text-slate-500 mb-1">MAM Strategies</div><div className="text-2xl font-bold">{mamCount}</div></div>
        <div className="stat"><div className="text-xs text-slate-500 mb-1">Copy Strategies</div><div className="text-2xl font-bold">{copyCount}</div></div>
        <div className="stat"><div className="text-xs text-slate-500 mb-1">Sagas</div><div className="text-2xl font-bold">{sagas?.length ?? 0}</div></div>
      </div>
      <div className="card p-4 mb-6">
        <h2 className="font-semibold mb-3">Outbox & Audit Status</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <div><div className="text-xs text-slate-500">Outbox Pending</div><div className="font-bold">{outboxStats?.pending ?? 0}</div></div>
          <div><div className="text-xs text-slate-500">Outbox Delivered</div><div className="font-bold">{outboxStats?.delivered ?? 0}</div></div>
          <div><div className="text-xs text-slate-500">Dead-Letter</div><div className="font-bold text-red-600">{outboxStats?.dead_letter ?? 0}</div></div>
          <div><div className="text-xs text-slate-500">Audit Chain</div>
            <div className={`font-bold ${audit?.verified ? 'text-green-600' : 'text-red-600'}`}>
              {audit?.verified ? 'INTACT' : 'TAMPERED'}
            </div>
          </div>
        </div>
      </div>
      <div className="card p-4">
        <h2 className="font-semibold mb-3">Master Accounts</h2>
        <table className="w-full text-sm">
          <thead className="text-left text-slate-500 border-b border-slate-200 dark:border-slate-700">
            <tr><th className="py-2">Login</th><th>Method</th><th>Equity</th><th>NAV</th><th>HWM</th><th>Fee Rate</th></tr>
          </thead>
          <tbody>
            {(masters || []).map(m => (
              <tr key={m.id} className="border-b border-slate-100 dark:border-slate-800">
                <td className="py-2 font-mono">{m.login}</td>
                <td><span className="tag-warn">{m.allocation_method}</span></td>
                <td>${Number(m.equity).toFixed(2)}</td>
                <td>${Number(m.nav).toFixed(4)}</td>
                <td>${Number(m.hwm).toFixed(2)}</td>
                <td>{(Number(m.performance_fee_rate) * 100).toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
