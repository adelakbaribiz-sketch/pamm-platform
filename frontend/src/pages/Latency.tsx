import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'
import { PageHeader } from '../components/ui'

export default function Latency() {
  const qc = useQueryClient()
  const [destination, setDestination] = useState('mt5-simulated')
  const [symbol, setSymbol] = useState('EURUSD')
  const [prediction, setPrediction] = useState<any>(null)
  const [observeActual, setObserveActual] = useState('80')
  const [observeSlippage, setObserveSlippage] = useState('1.5')
  const [calibration, setCalibration] = useState<any>(null)
  const [profile, setProfile] = useState<any>(null)
  const [err, setErr] = useState('')

  const predictM = useMutation({
    mutationFn: () => api.predictLatency({ destination, symbol, order_size: '1.0', recent_volatility: 0.1 }),
    onSuccess: (r) => { setPrediction(r); setErr('') },
    onError: (e: any) => setErr(e.message),
  })
  const observeM = useMutation({
    mutationFn: () => api.observeLatency({
      destination, symbol, order_size: '1.0',
      latency_ms: Number(observeActual), slippage_bps: observeSlippage,
      prediction_id: prediction?.prediction_id,
    }),
    onSuccess: (r) => { setPrediction({...prediction, observed: r}); qc.invalidateQueries({ queryKey: ['calib'] }) },
    onError: (e: any) => setErr(e.message),
  })
  const fetchCalib = async () => {
    try { setCalibration(await api.getCalibration(destination, symbol)) } catch (e: any) { setErr(e.message) }
  }
  const fetchProfile = async () => {
    try { setProfile(await api.getLatencyProfile(destination, symbol)) } catch (e: any) { setErr(e.message) }
  }

  return (
    <div>
      <PageHeader eyebrow="Infrastructure" title="Latency & slippage model" subtitle="Shadow model that predicts execution latency and slippage per destination, calibrated against observed fills." />
      <div className="card p-4 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
          <div><label className="label">Destination</label><input className="input" value={destination} onChange={e => setDestination(e.target.value)} /></div>
          <div><label className="label">Symbol</label><input className="input" value={symbol} onChange={e => setSymbol(e.target.value)} /></div>
          <div className="flex items-end"><button className="btn-primary w-full" onClick={() => predictM.mutate()} disabled={predictM.isPending}>Predict</button></div>
        </div>
        {err && <div className="text-red-500 text-xs">{err}</div>}
      </div>
      {prediction && (
        <div className="card p-4 mb-6">
          <h2 className="font-semibold mb-3">Prediction {prediction.observed && '(observed)'}</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm mb-4">
            <div><div className="text-xs text-slate-500">Prediction ID</div><div className="font-mono text-xs">{prediction.prediction_id?.slice(0, 8)}</div></div>
            <div><div className="text-xs text-slate-500">Predicted Latency</div><div className="font-bold">{prediction.predicted_latency_ms} ms</div></div>
            <div><div className="text-xs text-slate-500">95% Interval</div><div className="text-xs">[{prediction.predicted_lower_ms}, {prediction.predicted_upper_ms}] ms</div></div>
            <div><div className="text-xs text-slate-500">Predicted Slippage</div><div className="font-bold">{prediction.predicted_slippage_bps} bps</div></div>
            <div><div className="text-xs text-slate-500">Throttle Applied</div><div>{prediction.throttle_applied ? <span className="tag-warn">YES</span> : <span className="tag-ok">NO</span>}</div></div>
            <div><div className="text-xs text-slate-500">Model</div><div>{prediction.model_version}</div></div>
            {prediction.observed && (
              <>
                <div><div className="text-xs text-slate-500">Actual Latency</div><div className="font-bold">{prediction.observed.actual_latency_ms} ms</div></div>
                <div><div className="text-xs text-slate-500">Residual</div><div className={Number(prediction.observed.residual_latency) >= 0 ? 'text-red-600' : 'text-green-600'}>{prediction.observed.residual_latency} ms</div></div>
              </>
            )}
          </div>
          {!prediction.observed && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
              <div><label className="label">Actual Latency (ms)</label><input className="input" value={observeActual} onChange={e => setObserveActual(e.target.value)} /></div>
              <div><label className="label">Actual Slippage (bps)</label><input className="input" value={observeSlippage} onChange={e => setObserveSlippage(e.target.value)} /></div>
              <button className="btn-primary" onClick={() => observeM.mutate()} disabled={observeM.isPending}>Observe (close loop)</button>
            </div>
          )}
        </div>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-4">
          <div className="flex justify-between items-center mb-3">
            <h2 className="font-semibold">Execution Profile</h2>
            <button className="btn-ghost text-xs" onClick={fetchProfile}>Refresh</button>
          </div>
          {!profile ? <p className="text-slate-500 text-sm">Click Refresh.</p> :
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-slate-500">Total observations</span><span>{profile.total_observations}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Latency mean</span><span>{profile.latency_mean_ms} ms</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Latency std</span><span>{profile.latency_std_ms} ms</span></div>
              <div className="flex justify-between"><span className="text-slate-500">p50</span><span>{profile.latency_p50_ms} ms</span></div>
              <div className="flex justify-between"><span className="text-slate-500">p95</span><span>{profile.latency_p95_ms} ms</span></div>
              <div className="flex justify-between"><span className="text-slate-500">p99</span><span>{profile.latency_p99_ms} ms</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Slippage mean</span><span>{profile.slippage_mean_bps} bps</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Slippage std</span><span>{profile.slippage_std_bps} bps</span></div>
            </div>
          }
        </div>
        <div className="card p-4">
          <div className="flex justify-between items-center mb-3">
            <h2 className="font-semibold">Calibration Stats</h2>
            <button className="btn-ghost text-xs" onClick={fetchCalib}>Refresh</button>
          </div>
          {!calibration ? <p className="text-slate-500 text-sm">Click Refresh.</p> :
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-slate-500">N predictions observed</span><span>{calibration.n}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">MAE (latency)</span><span>{calibration.mae_ms} ms</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Bias (latency)</span><span className={Number(calibration.bias_ms) >= 0 ? 'text-red-600' : 'text-green-600'}>{calibration.bias_ms} ms</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Within 95% interval</span><span className="font-bold">{calibration.within_95pct_interval_pct}%</span></div>
            </div>
          }
        </div>
      </div>
    </div>
  )
}
