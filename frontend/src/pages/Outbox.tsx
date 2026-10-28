import React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'

export default function Outbox() {
  const qc = useQueryClient()
  const { data: stats } = useQuery({ queryKey: ['outbox-stats'], queryFn: api.outboxStats, refetchInterval: 5000 })
  const drain = useMutation({ mutationFn: () => api.drainOutbox(500),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['outbox-stats'] }) })

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Outbox</h1>
      <div className="card p-4 mb-6">
        <div className="grid grid-cols-3 gap-4 mb-4">
          <div className="stat"><div className="text-xs text-slate-500 mb-1">Pending</div><div className="text-2xl font-bold text-amber-600">{stats?.pending ?? 0}</div></div>
          <div className="stat"><div className="text-xs text-slate-500 mb-1">Delivered</div><div className="text-2xl font-bold text-green-600">{stats?.delivered ?? 0}</div></div>
          <div className="stat"><div className="text-xs text-slate-500 mb-1">Dead-Letter</div><div className="text-2xl font-bold text-red-600">{stats?.dead_letter ?? 0}</div></div>
        </div>
        <button className="btn-primary" onClick={() => drain.mutate()} disabled={drain.isPending}>
          {drain.isPending ? 'Draining…' : 'Drain Pending Now'}
        </button>
      </div>
      <div className="card p-4">
        <h2 className="font-semibold mb-3">About</h2>
        <p className="text-sm text-slate-500">
          The outbox holds pending event-publish tasks. In production these would be drained by a
          separate worker that publishes to Redis Streams (consumer groups) with idempotent consumers.
          For M3 we expose a manual drain endpoint that marks rows delivered; re-draining is safe
          (idempotent). Rows that fail repeatedly (missing event) move to dead-letter status for
          manual inspection.
        </p>
      </div>
    </div>
  )
}
