import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'

const STATUS_COLORS: Record<string, string> = {
  completed: 'tag-ok',
  failed: 'tag-danger',
  compensating: 'tag-warn',
  pending: 'tag-mock',
  running: 'tag-mock',
  abandoned: 'tag-danger',
}

export default function Sagas() {
  const qc = useQueryClient()
  const { data: sagas } = useQuery({ queryKey: ['sagas'], queryFn: api.listSagas })
  const [selected, setSelected] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const { data: detail } = useQuery({
    queryKey: ['saga', selected],
    queryFn: () => api.getSaga(selected!),
    enabled: !!selected,
  })
  const recover = useMutation({
    mutationFn: (saga_id: string) => api.recoverSaga(saga_id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sagas'] })
      qc.invalidateQueries({ queryKey: ['saga', selected] })
    },
  })

  const filtered = (sagas || []).filter(s => !statusFilter || s.status === statusFilter)
  const stats = {
    total: (sagas || []).length,
    completed: (sagas || []).filter(s => s.status === 'completed').length,
    failed: (sagas || []).filter(s => s.status === 'failed').length,
    compensating: (sagas || []).filter(s => s.status === 'compensating').length,
    pending: (sagas || []).filter(s => s.status === 'pending' || s.status === 'running').length,
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Settlement Sagas (P-3)</h1>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <div className="stat"><div className="text-xs text-slate-500 mb-1">Total Sagas</div><div className="text-2xl font-bold">{stats.total}</div></div>
        <div className="stat"><div className="text-xs text-slate-500 mb-1">Completed</div><div className="text-2xl font-bold text-green-600">{stats.completed}</div></div>
        <div className="stat"><div className="text-xs text-slate-500 mb-1">Failed</div><div className="text-2xl font-bold text-red-600">{stats.failed}</div></div>
        <div className="stat"><div className="text-xs text-slate-500 mb-1">Compensating</div><div className="text-2xl font-bold text-amber-600">{stats.compensating}</div></div>
        <div className="stat"><div className="text-xs text-slate-500 mb-1">Pending / Running</div><div className="text-2xl font-bold text-slate-600">{stats.pending}</div></div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-4">
          <div className="flex justify-between items-center mb-3">
            <h2 className="font-semibold">Saga List</h2>
            <select className="input text-xs w-40" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
              <option value="">All statuses</option>
              <option value="completed">completed</option>
              <option value="failed">failed</option>
              <option value="compensating">compensating</option>
              <option value="running">running</option>
              <option value="pending">pending</option>
              <option value="abandoned">abandoned</option>
            </select>
          </div>
          <table className="w-full text-sm">
            <thead className="text-left text-slate-500 border-b border-slate-200 dark:border-slate-700">
              <tr>
                <th className="py-2">Saga ID</th>
                <th>Kind</th>
                <th>Status</th>
                <th>Steps</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(s => (
                <tr
                  key={s.saga_id}
                  className={`border-t border-slate-100 dark:border-slate-800 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-700/40 ${selected === s.saga_id ? 'bg-brand-50 dark:bg-brand-700/20' : ''}`}
                  onClick={() => setSelected(s.saga_id)}
                >
                  <td className="py-2 font-mono text-xs">{s.saga_id.slice(0, 8)}</td>
                  <td>{s.kind}</td>
                  <td><span className={STATUS_COLORS[s.status] || 'tag-mock'}>{s.status}</span></td>
                  <td className="text-xs">
                    {(s.completed_steps || []).length} ✓
                    {s.failed_step && <span className="text-red-600 ml-1">· 1 ✗</span>}
                  </td>
                  <td className="text-xs">{new Date(s.created_at).toLocaleString()}</td>
                  <td>
                    {s.status !== 'completed' && s.status !== 'abandoned' && (
                      <button
                        className="btn-ghost text-xs"
                        disabled={recover.isPending}
                        onClick={(e) => { e.stopPropagation(); recover.mutate(s.saga_id) }}
                      >Recover</button>
                    )}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={6} className="py-4 text-center text-slate-500">No sagas match this filter.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="card p-4">
          <h2 className="font-semibold mb-3">Saga Detail</h2>
          {!selected ? (
            <p className="text-slate-500 text-sm">Select a saga on the left to inspect its steps, status, and compensation log.</p>
          ) : !detail ? (
            <p className="text-slate-500 text-sm">Loading…</p>
          ) : (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-2 pb-3 border-b border-slate-200 dark:border-slate-700">
                <div><span className="text-slate-500 text-xs">Saga ID</span><div className="font-mono text-xs break-all">{detail.saga_id}</div></div>
                <div><span className="text-slate-500 text-xs">Kind</span><div className="font-medium">{detail.kind}</div></div>
                <div><span className="text-slate-500 text-xs">Status</span>
                  <div><span className={STATUS_COLORS[detail.status] || 'tag-mock'}>{detail.status}</span></div>
                </div>
                <div><span className="text-slate-500 text-xs">Idempotency Key</span><div className="font-mono text-xs">{detail.idempotency_key || '—'}</div></div>
              </div>
              {detail.failed_step && (
                <div className="bg-red-50 dark:bg-red-900/20 p-3 rounded border border-red-300 dark:border-red-700">
                  <div className="text-xs text-red-700 dark:text-red-300 font-medium">Failed Step: {detail.failed_step}</div>
                  {detail.failure_reason && <div className="text-xs text-red-600 dark:text-red-400 mt-1">{detail.failure_reason}</div>}
                </div>
              )}
              <div>
                <div className="text-slate-500 text-xs mb-1">Steps (ordered):</div>
                <ol className="list-decimal ml-5 space-y-1.5">
                  {detail.step_records.map((s: any) => (
                    <li key={s.step_name} className="text-xs">
                      <div className="flex items-center gap-2 flex-wrap">
                        <strong className="font-mono">{s.step_name}</strong>
                        <span className={
                          s.status === 'completed' ? 'text-green-600 font-medium' :
                          s.status === 'failed' ? 'text-red-600 font-medium' :
                          s.status === 'compensated' ? 'text-amber-600 font-medium' :
                          s.status === 'running' ? 'text-blue-600 font-medium' :
                          'text-slate-500'
                        }>{s.status}</span>
                        {s.is_reversible ? (
                          <span className="text-xs text-green-700 dark:text-green-400">↩ reversible</span>
                        ) : (
                          <span className="text-xs text-red-700 dark:text-red-400 font-medium">⚠ IRREVERSIBLE → remediate</span>
                        )}
                        {s.attempts > 1 && <span className="text-amber-700 dark:text-amber-300">attempts={s.attempts}</span>}
                      </div>
                      {s.error && <div className="text-red-500 text-xs ml-3 mt-0.5">{s.error}</div>}
                      {s.compensation_action && s.status === 'compensated' && (
                        <div className="text-xs text-amber-700 dark:text-amber-300 ml-3 mt-0.5">
                          Compensation: <strong>{s.compensation_action}</strong>
                          {s.compensation_payload && s.compensation_payload.remediation_required &&
                            <span> — manual remediation required</span>}
                        </div>
                      )}
                    </li>
                  ))}
                </ol>
              </div>
              {detail.compensation_log && detail.compensation_log.length > 0 && (
                <div>
                  <div className="text-slate-500 text-xs mb-1">Compensation Log:</div>
                  <pre className="bg-slate-100 dark:bg-slate-900 p-2 rounded text-xs mt-1 overflow-x-auto">{JSON.stringify(detail.compensation_log, null, 2)}</pre>
                </div>
              )}
              {detail.status !== 'completed' && detail.status !== 'abandoned' && (
                <button
                  className="btn-primary w-full"
                  disabled={recover.isPending}
                  onClick={() => recover.mutate(detail.saga_id)}
                >
                  {recover.isPending ? 'Recovering…' : 'Recover Saga'}
                </button>
              )}
              {detail.status === 'completed' && (
                <div className="text-xs text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-900/20 p-2 rounded">
                  ✓ Saga completed successfully. All steps either succeeded or were compensated.
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
