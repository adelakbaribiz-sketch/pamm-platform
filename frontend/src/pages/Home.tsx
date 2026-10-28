import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  AreaChart, Area, BarChart, Bar, Legend,
} from 'recharts'
import { api } from '../api'
import { useAuth } from '../auth'

const COLORS = ['#2563eb', '#16a34a', '#f59e0b', '#dc2626', '#8b5cf6', '#ec4899']

export default function Home() {
  const { session } = useAuth()
  const qc = useQueryClient()
  const [selectedAccount, setSelectedAccount] = useState<string | null>(null)
  const [showInvestModal, setShowInvestModal] = useState<string | null>(null)
  const [investAmount, setInvestAmount] = useState('1000')

  const { data: stats } = useQuery({ queryKey: ['platform-stats'], queryFn: api.platformStats })
  const { data: topAccounts, isLoading: loadingAccounts } = useQuery({
    queryKey: ['top-accounts'], queryFn: () => api.topAccounts(10, 'return_pct'),
  })
  const { data: strategies } = useQuery({ queryKey: ['public-strategies'], queryFn: api.publicStrategies })

  const subscribe = useMutation({
    mutationFn: (body: any) => api.subscribe(body),
    onSuccess: () => { setShowInvestModal(null); qc.invalidateQueries({ queryKey: ['public-strategies'] }) },
  })

  // Aggregate P&L chart data across all top accounts
  const aggregateChart = (topAccounts || []).map((acc: any) => ({
    name: acc.login,
    equity: Number(acc.equity),
    return: Number(acc.return_pct),
    aum: Number(acc.equity),
  }))

  // Selected account P&L history
  const selected = (topAccounts || []).find((a: any) => a.master_account_id === selectedAccount)
  const pnlHistory = selected?.pnl_history || []

  return (
    <div className="space-y-6">
      {/* Hero Section */}
      <div className="card p-8 bg-gradient-to-r from-brand-500 to-brand-700 text-white border-0">
        <h1 className="text-3xl font-bold mb-2">پلتفرم PAMM / MAM / کپی تریدینگ</h1>
        <p className="text-brand-50 mb-6">سرمایه‌گذاری در استراتژی‌های حرفه‌ای با شفافیت کامل</p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white/10 rounded-lg p-4 backdrop-blur">
            <div className="text-xs text-brand-50 mb-1">مدیران فعال</div>
            <div className="text-2xl font-bold">{stats?.total_masters ?? '—'}</div>
          </div>
          <div className="bg-white/10 rounded-lg p-4 backdrop-blur">
            <div className="text-xs text-brand-50 mb-1">استراتژی‌ها</div>
            <div className="text-2xl font-bold">{stats?.total_strategies ?? '—'}</div>
          </div>
          <div className="bg-white/10 rounded-lg p-4 backdrop-blur">
            <div className="text-xs text-brand-50 mb-1">سرمایه‌گذاران</div>
            <div className="text-2xl font-bold">{stats?.total_active_investors ?? '—'}</div>
          </div>
          <div className="bg-white/10 rounded-lg p-4 backdrop-blur">
            <div className="text-xs text-brand-50 mb-1">دارایی تحت مدیریت</div>
            <div className="text-2xl font-bold">${Number(stats?.total_aum || 0).toLocaleString()}</div>
          </div>
        </div>
      </div>

      {/* Aggregate P&L Chart */}
      <div className="card p-6">
        <h2 className="text-lg font-semibold mb-4">عملکرد اکانت‌های برتر (سود/زیان)</h2>
        {aggregateChart.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={aggregateChart}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="name" stroke="#9ca3af" style={{ fontSize: 12 }} />
              <YAxis stroke="#9ca3af" style={{ fontSize: 12 }} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #374151', borderRadius: '8px' }}
                labelStyle={{ color: '#e2e8f0' }}
              />
              <Legend />
              <Bar dataKey="return" name="بازدهی %" fill="#16a34a" radius={[4, 4, 0, 0]} />
              <Bar dataKey="equity" name="دارایی ($)" fill="#2563eb" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-slate-500 text-center py-8">در حال بارگذاری داده‌ها...</p>
        )}
      </div>

      {/* Top Performing Accounts Grid */}
      <div>
        <h2 className="text-lg font-semibold mb-4">اکانت‌های موفق</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {(topAccounts || []).map((acc: any, idx: number) => (
            <div
              key={acc.master_account_id}
              className={`card p-5 cursor-pointer transition hover:shadow-lg ${selectedAccount === acc.master_account_id ? 'ring-2 ring-brand-500' : ''}`}
              onClick={() => setSelectedAccount(acc.master_account_id)}
            >
              <div className="flex items-center justify-between mb-3">
                <div>
                  <div className="font-bold text-lg">{acc.login}</div>
                  <div className="text-xs text-slate-500">مدیر: {acc.manager_name}</div>
                </div>
                <div className={`px-2 py-1 rounded text-xs font-bold ${
                  Number(acc.return_pct) >= 0 ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                }`}>
                  {Number(acc.return_pct) >= 0 ? '▲' : '▼'} {Math.abs(Number(acc.return_pct))}%
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm mb-3">
                <div>
                  <div className="text-xs text-slate-500">دارایی</div>
                  <div className="font-bold">${Number(acc.equity).toLocaleString()}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-500">NAV</div>
                  <div className="font-bold">${Number(acc.nav).toFixed(4)}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-500">سرمایه‌گذاران</div>
                  <div className="font-bold">{acc.subscriber_count}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-500">کارمزد</div>
                  <div className="font-bold">{(Number(acc.performance_fee_rate) * 100).toFixed(0)}%</div>
                </div>
              </div>
              {/* Mini sparkline */}
              {acc.pnl_history.length > 0 && (
                <ResponsiveContainer width="100%" height={60}>
                  <AreaChart data={acc.pnl_history}>
                    <defs>
                      <linearGradient id={`grad-${idx}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={COLORS[idx % COLORS.length]} stopOpacity={0.8} />
                        <stop offset="100%" stopColor={COLORS[idx % COLORS.length]} stopOpacity={0.1} />
                      </linearGradient>
                    </defs>
                    <Area
                      type="monotone"
                      dataKey="nav"
                      stroke={COLORS[idx % COLORS.length]}
                      strokeWidth={2}
                      fill={`url(#grad-${idx})`}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </div>
          ))}
          {loadingAccounts && (
            <div className="card p-8 text-center text-slate-500">در حال بارگذاری...</div>
          )}
        </div>
      </div>

      {/* Detailed P&L Chart for Selected Account */}
      {selected && (
        <div className="card p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-lg font-semibold">نمودار سود و زیان: {selected.login}</h2>
              <p className="text-sm text-slate-500">
                استراتژی: {selected.strategy_name} ({selected.strategy_kind}) ·
                بازدهی: {selected.return_pct}% ·
                سرمایه‌گذاران: {selected.subscriber_count}
              </p>
            </div>
            {session && session.role !== 'super_admin' && (
              <button
                className="btn-primary"
                onClick={() => setShowInvestModal(selected.strategy_id)}
              >
                سرمایه‌گذاری در این استراتژی
              </button>
            )}
          </div>

          {pnlHistory.length > 0 ? (
            <>
              <div className="mb-6">
                <h3 className="text-sm font-medium text-slate-500 mb-2">NAV (ارزش خالص دارایی)</h3>
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={pnlHistory}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis
                      dataKey="date"
                      stroke="#9ca3af"
                      style={{ fontSize: 11 }}
                      tickFormatter={(v: any) => v ? new Date(v as string).toLocaleDateString("fa-IR") : ""}
                    />
                    <YAxis stroke="#9ca3af" style={{ fontSize: 12 }} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #374151', borderRadius: '8px' }}
                      labelStyle={{ color: '#e2e8f0' }}
                      labelFormatter={(v: any) => v ? new Date(v as string).toLocaleString("fa-IR") : ""}
                    />
                    <Legend />
                    <Line type="monotone" dataKey="nav" name="NAV" stroke="#2563eb" strokeWidth={2} dot={{ r: 3 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              <div className="mb-6">
                <h3 className="text-sm font-medium text-slate-500 mb-2">سود/زیان تجمعی</h3>
                <ResponsiveContainer width="100%" height={280}>
                  <AreaChart data={pnlHistory}>
                    <defs>
                      <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#16a34a" stopOpacity={0.6} />
                        <stop offset="100%" stopColor="#16a34a" stopOpacity={0.05} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis
                      dataKey="date"
                      stroke="#9ca3af"
                      style={{ fontSize: 11 }}
                      tickFormatter={(v: any) => v ? new Date(v as string).toLocaleDateString("fa-IR") : ""}
                    />
                    <YAxis stroke="#9ca3af" style={{ fontSize: 12 }} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #374151', borderRadius: '8px' }}
                      labelStyle={{ color: '#e2e8f0' }}
                      labelFormatter={(v: any) => v ? new Date(v as string).toLocaleString("fa-IR") : ""}
                    />
                    <Legend />
                    <Area
                      type="monotone"
                      dataKey="cumulative_pnl"
                      name="سود تجمعی"
                      stroke="#16a34a"
                      strokeWidth={2}
                      fill="url(#pnlGrad)"
                    />
                    <Bar dataKey="pnl" name="سود دوره" fill="#f59e0b" opacity={0.6} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              <div>
                <h3 className="text-sm font-medium text-slate-500 mb-2">کارمزد عملکرد جمع‌آوری شده</h3>
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={pnlHistory}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis
                      dataKey="date"
                      stroke="#9ca3af"
                      style={{ fontSize: 11 }}
                      tickFormatter={(v: any) => v ? new Date(v as string).toLocaleDateString("fa-IR") : ""}
                    />
                    <YAxis stroke="#9ca3af" style={{ fontSize: 12 }} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #374151', borderRadius: '8px' }}
                      labelStyle={{ color: '#e2e8f0' }}
                    />
                    <Bar dataKey="total_fee" name="کارمزد ($)" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>
          ) : (
            <p className="text-slate-500 text-center py-8">داده‌ای برای نمایش وجود ندارد.</p>
          )}
        </div>
      )}

      {/* Investment Opportunities */}
      <div>
        <h2 className="text-lg font-semibold mb-4">فرصت‌های سرمایه‌گذاری</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {(strategies || []).map((s: any) => (
            <div key={s.strategy_id} className="card p-5">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <div className="font-bold">{s.name}</div>
                  <div className="text-xs text-slate-500">{s.master_login} · {s.currency}</div>
                </div>
                <span className={`tag ${s.kind === 'pamm' ? 'tag-ok' : s.kind === 'mam' ? 'tag-warn' : 'tag-mock'}`}>
                  {s.kind.toUpperCase()}
                </span>
              </div>
              {s.description && <p className="text-sm text-slate-500 mb-3">{s.description}</p>}
              <div className="grid grid-cols-2 gap-3 text-sm mb-4">
                <div>
                  <div className="text-xs text-slate-500">بازدهی</div>
                  <div className={`font-bold ${Number(s.return_pct) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {Number(s.return_pct) >= 0 ? '+' : ''}{s.return_pct}%
                  </div>
                </div>
                <div>
                  <div className="text-xs text-slate-500">NAV</div>
                  <div className="font-bold">${Number(s.nav).toFixed(4)}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-500">سرمایه‌گذاران</div>
                  <div className="font-bold">{s.subscriber_count}</div>
                </div>
                <div>
                  <div className="text-xs text-slate-500">کارمزد سود</div>
                  <div className="font-bold">{(Number(s.performance_fee_rate) * 100).toFixed(0)}%</div>
                </div>
              </div>
              <div className="text-xs text-slate-500 mb-3">
                حداقل سرمایه‌گذاری: ${s.min_investment}
              </div>
              {session ? (
                <button
                  className="btn-primary w-full"
                  onClick={() => setShowInvestModal(s.strategy_id)}
                >
                  سرمایه‌گذاری
                </button>
              ) : (
                <a href="/login" className="btn-primary w-full block text-center">ورود برای سرمایه‌گذاری</a>
              )}
            </div>
          ))}
          {strategies && strategies.length === 0 && (
            <div className="card p-8 text-center text-slate-500 col-span-3">
              در حال حاضر استراتژی فعالی وجود ندارد.
            </div>
          )}
        </div>
      </div>

      {/* Invest Modal */}
      {showInvestModal && (
        <InvestModal
          strategyId={showInvestModal}
          amount={investAmount}
          setAmount={setInvestAmount}
          onClose={() => setShowInvestModal(null)}
          onConfirm={() => {
            // Need investor account — for simplicity, use the first one
            api.listInvestors().then(inv => {
              if (inv.length === 0) {
                alert('ابتدا یک حساب سرمایه‌گذار ایجاد کنید (صفحه Investors)')
                return
              }
              subscribe.mutate({
                strategy_id: showInvestModal,
                investor_account_id: inv[0].id,
                capital: investAmount,
              })
            })
          }}
          pending={subscribe.isPending}
          error={subscribe.isError ? String(subscribe.error) : ''}
        />
      )}
    </div>
  )
}

function InvestModal({ strategyId, amount, setAmount, onClose, onConfirm, pending, error }:
  { strategyId: string; amount: string; setAmount: (v: string) => void;
    onClose: () => void; onConfirm: () => void; pending: boolean; error: string }) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="card p-6 w-full max-w-md" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h3 className="font-semibold">سرمایه‌گذاری در استراتژی</h3>
          <button onClick={onClose} className="text-slate-400">✕</button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="label">مبلغ سرمایه‌گذاری ($)</label>
            <input
              type="number"
              className="input"
              value={amount}
              onChange={e => setAmount(e.target.value)}
              min="100"
            />
            <p className="text-xs text-slate-500 mt-1">حداقل مبلغ: $100</p>
          </div>
          {error && <div className="text-red-500 text-sm">{error}</div>}
          <button className="btn-primary w-full" onClick={onConfirm} disabled={pending || Number(amount) < 100}>
            {pending ? 'در حال پردازش...' : 'تأیید سرمایه‌گذاری'}
          </button>
          <p className="text-xs text-slate-500">
            با تأیید، سرمایه شما به استراتژی مورد نظر اضافه می‌شود و واحد‌های PAMM صادر می‌گردد.
            کارمزد عملکرد تنها در صورت کسب سود جدید (High-Water Mark) کسر می‌شود.
          </p>
        </div>
      </div>
    </div>
  )
}
