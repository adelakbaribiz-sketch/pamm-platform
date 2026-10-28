import { useQuery } from '@tanstack/react-query'
import { api } from './api'
import { maxDrawdown } from './format'

export interface PerfPoint { date: string; nav: number; pnl: number; cumulative_pnl: number; total_fee: number; equity: number | null }

export interface AccountPerf {
  master_account_id: string
  strategy_id: string | null
  login: string
  manager_name: string
  manager_id: string | null
  strategy_name: string | null
  strategy_kind: string
  currency: string
  equity: number
  nav: number
  return_pct: number
  subscriber_count: number
  performance_fee_rate: number
  allocation_method: string
  history: PerfPoint[]
  max_drawdown: number
  fees_collected: number
  weeks: number
}

/** Public per-master performance (rollover history), normalised to numbers. */
export function useAccountPerformance() {
  return useQuery({
    queryKey: ['top-accounts'],
    queryFn: () => api.topAccounts(50, 'return_pct'),
    select: (rows: any[]): AccountPerf[] => rows.map(r => {
      const history: PerfPoint[] = (r.pnl_history || []).map((p: any) => ({ ...p, nav: Number(p.nav) }))
      return {
        ...r,
        equity: Number(r.equity), nav: Number(r.nav), return_pct: Number(r.return_pct),
        performance_fee_rate: Number(r.performance_fee_rate),
        history,
        max_drawdown: maxDrawdown([Number(r.base_nav || 100), ...history.map(h => h.nav)]),
        fees_collected: history.reduce((s, h) => s + (h.total_fee || 0), 0),
        weeks: history.length,
      }
    }),
  })
}
