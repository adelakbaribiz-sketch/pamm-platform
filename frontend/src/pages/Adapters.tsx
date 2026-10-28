import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'

const ADAPTER_TYPE_COLORS: Record<string, string> = {
  simulated: 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300',
  mt5: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300',
  ctrader: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-300',
  crypto: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
}

export default function Adapters() {
  const qc = useQueryClient()
  const { data: adapters, isLoading } = useQuery({ queryKey: ['adapters'], queryFn: () => api.listAdapters() })
  const [selected, setSelected] = useState<string | null>(null)
  const [testConnectResult, setTestConnectResult] = useState<any>(null)
  const { data: detail } = useQuery({
    queryKey: ['adapter', selected],
    queryFn: () => api.getAdapter(selected!),
    enabled: !!selected,
  })

  const testConnect = useMutation({
    mutationFn: (type: string) => api.testConnect(type),
    onSuccess: (r) => { setTestConnectResult(r); qc.invalidateQueries({ queryKey: ['adapters'] }) },
  })

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Broker Adapters</h1>
      <div className="card p-4 mb-6">
        <h2 className="font-semibold mb-3">Registered Adapters</h2>
        <p className="text-xs text-slate-500 mb-3">
          Each adapter implements the canonical ExecutionAdapter interface. BLOCKED adapters
          have their contract + capability matrix documented but require proprietary SDKs and
          broker credentials to operate. The simulated adapter is fully functional for development.
        </p>
        <table className="w-full text-sm">
          <thead className="text-left text-slate-500 border-b border-slate-200 dark:border-slate-700">
            <tr>
              <th className="py-2">Type</th>
              <th>Live</th>
              <th>Status</th>
              <th>Capabilities</th>
              <th>Lot Step</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {(adapters || []).map(a => (
              <tr
                key={a.type}
                className={`border-t border-slate-100 dark:border-slate-800 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-700/40 ${selected === a.type ? 'bg-brand-50 dark:bg-brand-700/20' : ''}`}
                onClick={() => setSelected(a.type)}
              >
                <td className="py-2">
                  <span className={`tag ${ADAPTER_TYPE_COLORS[a.type] || 'tag-mock'}`}>{a.type}</span>
                </td>
                <td>{a.is_live ? <span className="text-green-600 font-medium">YES</span> : <span className="text-slate-500">no</span>}</td>
                <td>
                  {a.blocked ? <span className="tag-danger">BLOCKED</span> : <span className="tag-ok">READY</span>}
                </td>
                <td className="text-xs text-slate-500">
                  {a.supports_market_orders ? '✓ market' : '✗ market'}
                  {' · '}
                  {a.supports_modify ? '✓ modify' : '✗ modify'}
                  {' · '}
                  {a.supports_partial_fills ? '✓ partial' : '✗ partial'}
                  {' · '}
                  {a.supports_reconciliation ? '✓ reconcile' : '✗ reconcile'}
                </td>
                <td className="font-mono text-xs">{a.lot_step}</td>
                <td>
                  <button
                    className="btn-ghost text-xs"
                    disabled={testConnect.isPending}
                    onClick={(e) => { e.stopPropagation(); testConnect.mutate(a.type) }}
                  >Test Connect</button>
                </td>
              </tr>
            ))}
            {adapters && adapters.length === 0 && (
              <tr><td colSpan={6} className="py-4 text-center text-slate-500">No adapters registered.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {testConnectResult && (
        <div className="card p-4 mb-6">
          <div className="flex justify-between items-center mb-3">
            <h2 className="font-semibold">Test-Connect Result: {testConnectResult.type}</h2>
            <button className="text-slate-400 text-xs" onClick={() => setTestConnectResult(null)}>✕</button>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm mb-3">
            <div><div className="text-xs text-slate-500">Connected</div>
              <div className="font-bold">
                {testConnectResult.connected ? <span className="text-green-600">YES</span> : <span className="text-red-600">NO</span>}
              </div>
            </div>
            <div><div className="text-xs text-slate-500">Is Live</div>
              <div className="font-bold">{testConnectResult.is_live ? 'YES' : 'NO'}</div>
            </div>
            {testConnectResult.blocked !== undefined && (
              <div><div className="text-xs text-slate-500">Blocked</div>
                <div className="font-bold">{testConnectResult.blocked ? 'YES' : 'NO'}</div>
              </div>
            )}
            {testConnectResult.code && (
              <div><div className="text-xs text-slate-500">Code</div>
                <div className="font-mono text-xs">{testConnectResult.code}</div>
              </div>
            )}
          </div>
          {testConnectResult.warning && (
            <div className="text-xs text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/20 p-2 rounded">
              {testConnectResult.warning}
            </div>
          )}
          {testConnectResult.reason && (
            <div className="text-xs text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/20 p-2 rounded mt-2">
              <strong>Reason:</strong> {testConnectResult.reason}
            </div>
          )}
        </div>
      )}

      {selected && detail && (
        <div className="card p-4">
          <h2 className="font-semibold mb-3">Adapter Detail: {detail.type}</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h3 className="text-sm font-medium mb-2">Capabilities</h3>
              <table className="w-full text-xs">
                <tbody>
                  {Object.entries(detail.capabilities).map(([k, v]) => (
                    <tr key={k} className="border-t border-slate-100 dark:border-slate-800">
                      <td className="py-1 font-mono">{k}</td>
                      <td className="text-right">
                        {v ? <span className="text-green-600">✓</span> : <span className="text-red-600">✗</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div>
              <h3 className="text-sm font-medium mb-2">Limits & Notes</h3>
              <div className="space-y-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-slate-500">Max lots / order</span>
                  <span className="font-mono">{detail.limits.max_lots_per_order || 'unlimited'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Lot step</span>
                  <span className="font-mono">{detail.limits.lot_step}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Is live</span>
                  <span className={detail.is_live ? 'text-green-600 font-medium' : 'text-red-600'}>
                    {detail.is_live ? 'YES' : 'NO'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Blocked</span>
                  <span className={detail.blocked ? 'text-red-600 font-medium' : 'text-green-600'}>
                    {detail.blocked ? 'YES' : 'NO'}
                  </span>
                </div>
                {detail.limits.supported_symbols.length > 0 && (
                  <div>
                    <div className="text-slate-500 mb-1">Supported symbols</div>
                    <div className="flex flex-wrap gap-1">
                      {detail.limits.supported_symbols.map((s: string) => (
                        <span key={s} className="tag-mock">{s}</span>
                      ))}
                    </div>
                  </div>
                )}
                <div className="pt-2 border-t border-slate-200 dark:border-slate-700">
                  <div className="text-slate-500 mb-1">Notes</div>
                  <div className="text-xs text-slate-700 dark:text-slate-300">{detail.notes}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
