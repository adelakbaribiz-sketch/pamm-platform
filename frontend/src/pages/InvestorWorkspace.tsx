import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'

export default function InvestorWorkspace() {
  const { data: subs } = useQuery({ queryKey: ['subs'], queryFn: api.listSubscriptions })
  const mySubs = subs || []
  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Investor Workspace</h1>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="stat"><div className="text-xs text-slate-500 mb-1">Total Subscriptions</div><div className="text-2xl font-bold">{mySubs.length}</div></div>
        <div className="stat"><div className="text-xs text-slate-500 mb-1">Total Contributed</div><div className="text-2xl font-bold">${mySubs.reduce((s, x) => s + Number(x.contributed_capital), 0).toFixed(2)}</div></div>
        <div className="stat"><div className="text-xs text-slate-500 mb-1">Total Unrealized P&L</div><div className={`text-2xl font-bold ${mySubs.reduce((s, x) => s + Number(x.unrealized_pnl), 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>${mySubs.reduce((s, x) => s + Number(x.unrealized_pnl), 0).toFixed(2)}</div></div>
      </div>
      <div className="card p-4">
        <h2 className="font-semibold mb-3">My Subscriptions</h2>
        <table className="w-full text-sm">
          <thead className="text-left text-slate-500"><tr><th className="py-2">Master</th><th>Capital</th><th>Units</th><th>NAV</th><th>GAV</th><th>P&L</th><th>HWM</th></tr></thead>
          <tbody>
            {mySubs.map(s => (
              <tr key={s.id} className="border-t border-slate-100 dark:border-slate-800">
                <td className="py-2 font-mono">{s.master_login}</td>
                <td>${Number(s.contributed_capital).toFixed(2)}</td>
                <td>{Number(s.units).toFixed(4)}</td>
                <td>${Number(s.current_nav).toFixed(4)}</td>
                <td>${Number(s.current_gav).toFixed(2)}</td>
                <td className={Number(s.unrealized_pnl) >= 0 ? 'text-green-600' : 'text-red-600'}>${Number(s.unrealized_pnl).toFixed(2)}</td>
                <td>${Number(s.hwm).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
