import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { api } from '../api'

export default function Managers() {
  const { data: managers, isLoading } = useQuery({
    queryKey: ['public-managers'], queryFn: () => api.publicManagers(20),
  })
  const [expanded, setExpanded] = useState<string | null>(null)

  // Aggregate AUM by manager for the bar chart
  const chartData = (managers || []).map((m: any) => ({
    name: m.manager_name,
    aum: Number(m.total_aum),
    subscribers: m.total_subscribers,
    return: Number(m.avg_return_pct),
  }))

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold mb-2">پرتفولیو مدیران سرمایه</h1>
        <p className="text-sm text-slate-500">فهرست مدیران حرفه‌ای با آمار عملکرد تجمعی</p>
      </div>

      {/* Aggregate AUM Chart */}
      {chartData.length > 0 && (
        <div className="card p-6">
          <h2 className="text-lg font-semibold mb-4">دارایی تحت مدیریت بر اساس مدیر</h2>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={chartData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis type="number" stroke="#9ca3af" style={{ fontSize: 12 }} tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} />
              <YAxis type="category" dataKey="name" stroke="#9ca3af" style={{ fontSize: 12 }} width={80} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #374151', borderRadius: '8px' }}
                labelStyle={{ color: '#e2e8f0' }}
                formatter={(v: any, name: any) => name === "aum" ? [`$${Number(v).toLocaleString()}`, "دارایی"] : [v, name]}
              />
              <Bar dataKey="aum" name="دارایی ($)" fill="#2563eb" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Manager Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {(managers || []).map((mgr: any) => (
          <div key={mgr.manager_id} className="card p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-brand-500 flex items-center justify-center text-white font-bold text-lg">
                  {mgr.manager_name.charAt(0).toUpperCase()}
                </div>
                <div>
                  <div className="font-bold text-lg">{mgr.manager_name}</div>
                  <div className="text-xs text-slate-500">
                    {mgr.master_account_count} اکانت · {mgr.total_subscribers} سرمایه‌گذار
                  </div>
                </div>
              </div>
              <div className={`px-3 py-1 rounded-lg text-sm font-bold ${
                Number(mgr.avg_return_pct) >= 0 ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
              }`}>
                {Number(mgr.avg_return_pct) >= 0 ? '▲' : '▼'} {Math.abs(Number(mgr.avg_return_pct))}%
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3 mb-4 text-sm">
              <div className="bg-slate-50 dark:bg-slate-900/40 rounded p-3">
                <div className="text-xs text-slate-500 mb-1">AUM کل</div>
                <div className="font-bold">${Number(mgr.total_aum).toLocaleString()}</div>
              </div>
              <div className="bg-slate-50 dark:bg-slate-900/40 rounded p-3">
                <div className="text-xs text-slate-500 mb-1">بازدهی متوسط</div>
                <div className={`font-bold ${Number(mgr.avg_return_pct) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {mgr.avg_return_pct}%
                </div>
              </div>
              <div className="bg-slate-50 dark:bg-slate-900/40 rounded p-3">
                <div className="text-xs text-slate-500 mb-1">استراتژی‌ها</div>
                <div className="font-bold">{mgr.strategies.length}</div>
              </div>
            </div>

            {/* Strategy list */}
            <div className="space-y-2">
              {mgr.strategies.map((s: any) => (
                <div key={s.strategy_id} className="border border-slate-200 dark:border-slate-700 rounded p-3 flex items-center justify-between">
                  <div>
                    <div className="font-medium text-sm">{s.name}</div>
                    <div className="text-xs text-slate-500">
                      {s.master_login} · {s.kind.toUpperCase()} · {s.subscriber_count} سرمایه‌گذار
                    </div>
                  </div>
                  <div className="text-right">
                    <div className={`text-sm font-bold ${Number(s.return_pct) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {s.return_pct}%
                    </div>
                    <div className="text-xs text-slate-500">${Number(s.equity).toLocaleString()}</div>
                  </div>
                </div>
              ))}
            </div>

            <a href="/#invest" className="btn-primary w-full mt-4 block text-center">
              مشاهده فرصت‌های سرمایه‌گذاری
            </a>
          </div>
        ))}
        {isLoading && (
          <div className="card p-8 text-center text-slate-500 col-span-2">در حال بارگذاری...</div>
        )}
        {!isLoading && managers && managers.length === 0 && (
          <div className="card p-8 text-center text-slate-500 col-span-2">
            هنوز مدیر فعالی ثبت نشده است.
          </div>
        )}
      </div>
    </div>
  )
}
