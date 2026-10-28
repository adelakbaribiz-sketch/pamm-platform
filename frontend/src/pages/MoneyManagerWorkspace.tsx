import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'

export default function MoneyManagerWorkspace() {
  const { data: masters } = useQuery({ queryKey: ['masters'], queryFn: api.listMasters })
  const { data: subs } = useQuery({ queryKey: ['subs'], queryFn: api.listSubscriptions })
  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Money Manager Workspace</h1>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-4">
          <h2 className="font-semibold mb-3">Managed Master Accounts</h2>
          <table className="w-full text-sm">
            <thead className="text-left text-slate-500"><tr><th className="py-2">Login</th><th>Equity</th><th>NAV</th><th>HWM</th><th>Fee Rate</th></tr></thead>
            <tbody>
              {(masters || []).map(m => (
                <tr key={m.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-2 font-mono">{m.login}</td>
                  <td>${Number(m.equity).toFixed(2)}</td>
                  <td>${Number(m.nav).toFixed(4)}</td>
                  <td>${Number(m.hwm).toFixed(2)}</td>
                  <td>{(Number(m.performance_fee_rate) * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="card p-4">
          <h2 className="font-semibold mb-3">Investor Participation</h2>
          <table className="w-full text-sm">
            <thead className="text-left text-slate-500"><tr><th className="py-2">Investor</th><th>Capital</th><th>GAV</th><th>Units</th></tr></thead>
            <tbody>
              {(subs || []).map(s => (
                <tr key={s.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-2 font-mono">{s.investor_login}</td>
                  <td>${Number(s.contributed_capital).toFixed(2)}</td>
                  <td>${Number(s.current_gav).toFixed(2)}</td>
                  <td>{Number(s.units).toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
