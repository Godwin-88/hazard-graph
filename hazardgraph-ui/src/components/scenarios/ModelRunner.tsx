import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Info } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import {
  fetchPipelineStatus,
  fetchJobHistory,
  runPipelineScope,
  runSingleModel,
  fetchRiskScores,
  fetchRegimes,
  fetchCausalEdges,
  fetchTemporalGraph,
  fetchAllForecasts,
  fetchPolicyRecommendations,
  type PipelineModel,
  type JobRunRecord,
} from '@/lib/api'
import type { PolicyRecommendation } from '@/types'

const REGIONS = [
  'kenya', 'ethiopia', 'somalia', 'sudan', 'south_sudan',
  'uganda', 'djibouti', 'eritrea', 'tanzania', 'burundi', 'rwanda',
]

const LAYER_ORDER = ['Ingestion', 'Stochastic', 'Causal', 'ML', 'Network', 'RL', 'Ensemble', 'Ops']

const LAYER_COLORS: Record<string, string> = {
  Ingestion: 'text-blue-400',
  Stochastic: 'text-emerald-400',
  Causal: 'text-purple-400',
  ML: 'text-amber-400',
  Network: 'text-pink-400',
  RL: 'text-cyan-400',
  Ensemble: 'text-risk-green',
  Ops: 'text-gray-400',
}

function statusColor(status: string): string {
  if (status === 'completed') return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30'
  if (status === 'running') return 'text-amber-400 bg-amber-500/10 border-amber-500/30 animate-pulse'
  if (status === 'failed') return 'text-red-400 bg-red-500/10 border-red-500/30'
  return 'text-gray-400 bg-gray-500/10 border-gray-500/30'
}

function fmtStatus(status: string): string {
  return status.replace('_', ' ')
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return 'never'
  const diffMs = Date.now() - new Date(dateStr).getTime()
  const min = Math.floor(diffMs / 60000)
  if (min < 1) return 'just now'
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ago`
  return `${Math.floor(hr / 24)}d ago`
}

export default function ModelRunner() {
  const queryClient = useQueryClient()
  const [scope, setScope] = useState<'full' | 'scoring' | 'models'>('full')
  const [selectedModels, setSelectedModels] = useState<string[]>([])
  const [selectedRegion, setSelectedRegion] = useState('somalia')
  const [forecastData, setForecastData] = useState<Awaited<ReturnType<typeof fetchAllForecasts>> | null>(null)
  const [loadingForecast, setLoadingForecast] = useState(false)

  // Data queries for the four analytics panels
  const statusQuery = useQuery({ queryKey: ['pipeline-status'], queryFn: fetchPipelineStatus })
  const jobsQuery = useQuery({ queryKey: ['pipeline-jobs'], queryFn: fetchJobHistory, refetchInterval: 5000 })
  const riskQuery = useQuery({ queryKey: ['risk-scores'], queryFn: fetchRiskScores })
  const regimesQuery = useQuery({ queryKey: ['regimes'], queryFn: fetchRegimes })
  const causalQuery = useQuery({ queryKey: ['causal-edges'], queryFn: fetchCausalEdges })
  const temporalQuery = useQuery({ queryKey: ['temporal-graph'], queryFn: fetchTemporalGraph })
  const policyQuery = useQuery({ queryKey: ['policy-recommendations'], queryFn: fetchPolicyRecommendations })

  const runPipelineMutation = useMutation({
    mutationFn: () => runPipelineScope(scope, selectedModels),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['pipeline-jobs'] })
      setScope('full')
      setSelectedModels([])
    },
  })

  const runModelMutation = useMutation({
    mutationFn: (name: string) => runSingleModel(name),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['pipeline-jobs'] })
    },
  })

  const loadForecast = async () => {
    const data = await fetchAllForecasts(selectedRegion)
    setForecastData(data)
  }

  const models = statusQuery.data?.models || []
  const jobs = jobsQuery.data?.jobs || []
  const regions = riskQuery.data?.regions || []
  const regimes = regimesQuery.data?.regions || []
  const causalEdges = causalQuery.data || []
  const snapshots = temporalQuery.data?.snapshots || []
  const recommendations: PolicyRecommendation[] = policyQuery.data?.recommendations || []

  // Group models by layer
  const byLayer = new Map<string, PipelineModel[]>()
  for (const m of models) {
    const layer = m.layer || 'Ops'
    if (!byLayer.has(layer)) byLayer.set(layer, [])
    byLayer.get(layer)!.push(m)
  }

  const toggleModel = (name: string) => {
    setSelectedModels((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name],
    )
  }

  const runningCount = jobs.filter((j) => j.status === 'running').length
  const failedCount = jobs.filter((j) => j.status === 'failed').slice(0, 20).length

  return (
    <div className="space-y-6">
      {/* Run pipeline panel */}
      <Card className="border-border/50 bg-[#12172B]">
        <CardHeader>
          <CardTitle className="text-white text-lg">Model Runner — On-Demand Execution</CardTitle>
          <CardDescription className="text-text-muted">
            Trigger the ML pipeline DAG or individual models. Runs execute in the background and are logged to job history.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {(['full', 'scoring', 'models'] as const).map((s) => (
              <button
                key={s}
                onClick={() => setScope(s)}
                className={`px-3 py-1.5 rounded text-xs font-medium border transition-colors capitalize ${
                  scope === s
                    ? 'bg-risk-green/20 text-risk-green border-risk-green/30'
                    : 'bg-[#0A0F1E] text-text-secondary border-border/50 hover:border-risk-green/50'
                }`}
              >
                {s === 'full' ? 'Full Pipeline DAG' : s === 'scoring' ? 'Scoring Only' : 'Select Models'}
              </button>
            ))}
          </div>

          {scope === 'models' && (
            <div className="flex flex-wrap gap-1.5">
              {models.map((m) => (
                <label key={m.name} className="flex items-center gap-1.5 px-2 py-1 rounded bg-[#0A0F1E] border border-border/50 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedModels.includes(m.name)}
                    onChange={() => toggleModel(m.name)}
                    className="rounded"
                  />
                  <span className="text-xs text-text-secondary">{m.name}</span>
                </label>
              ))}
            </div>
          )}

          <button
            onClick={() => runPipelineMutation.mutate()}
            disabled={runPipelineMutation.isPending}
            className="px-4 py-2 bg-risk-green/20 text-risk-green border border-risk-green/30 rounded hover:bg-risk-green/30 transition-colors text-sm"
          >
            {runPipelineMutation.isPending ? 'Starting...' : `Run ${scope === 'full' ? 'Full Pipeline' : scope === 'scoring' ? 'Scoring' : selectedModels.length + ' selected model(s)'}`}
          </button>

          {runPipelineMutation.isSuccess && (
            <div className="p-3 bg-risk-green/10 border border-risk-green/30 rounded text-risk-green text-xs">
              Pipeline started in background — monitor job history below.
            </div>
          )}
          {runPipelineMutation.isError && (
            <div className="p-3 bg-red-500/10 border border-red-500/30 rounded text-red-300 text-xs">
              {(runPipelineMutation.error as Error).message}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Descriptive panel */}
      <Card className="border-border/50 bg-[#12172B]">
        <CardHeader>
          <CardTitle className="text-white text-lg">Descriptive — Current System State</CardTitle>
          <CardDescription className="text-text-muted">What is happening across IGAD regions right now</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <h4 className="text-sm font-semibold text-white mb-2 flex items-center gap-1">
                Region Risk Scores
                <div className="group relative">
                  <Info className="h-3 w-3 cursor-help text-text-muted" />
                  <div className="absolute bottom-full left-0 mb-2 hidden w-48 rounded-lg bg-gray-900 p-2 text-xs text-gray-300 shadow-xl group-hover:block z-50">
                    BMA posterior risk score (0–100). Combines all model outputs weighted by recent accuracy.
                    Scores ≥60 trigger SMS alerts. Scores 30–59 are elevated. Scores &lt;30 are normal.
                  </div>
                </div>
              </h4>
              {riskQuery.isLoading && <LoadingSpinner />}
              <div className="space-y-1.5">
                {regions.slice(0, 8).map((r) => (
                  <div key={r.id} className="flex items-center gap-2 text-xs">
                    <span className="w-24 text-text-secondary capitalize truncate">{r.name}</span>
                    <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${r.score > 60 ? 'bg-red-500' : r.score > 30 ? 'bg-amber-500' : 'bg-risk-green'}`}
                        style={{ width: `${Math.min(r.score, 100)}%` }}
                      />
                    </div>
                    <span className="w-8 text-right text-text-secondary">{r.score.toFixed(0)}</span>
                    {r.score > 60 && <span className="text-[10px] text-risk-red font-semibold">⚠</span>}
                    {r.score <= 30 && <span className="text-[10px] text-risk-green">✓</span>}
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h4 className="text-sm font-semibold text-white mb-2 flex items-center gap-1">
                Regime Distribution
                <div className="group relative">
                  <Info className="h-3 w-3 cursor-help text-text-muted" />
                  <div className="absolute bottom-full left-0 mb-2 hidden w-56 rounded-lg bg-gray-900 p-2 text-xs text-gray-300 shadow-xl group-hover:block z-50">
                    Current climate regime detected by the Hidden Markov Model (HMM).
                    Regimes map to hazard states: Baseline (normal), DroughtOnset (dry trending),
                    SevereDrought (extreme dry), FloodWatch (wet trending), FloodEmergency (extreme wet).
                  </div>
                </div>
              </h4>
              {regimesQuery.isLoading && <LoadingSpinner />}
              <div className="space-y-1.5">
                {regimes.slice(0, 8).map((rg) => (
                  <div key={rg.id} className="flex items-center justify-between text-xs">
                    <span className="text-text-secondary capitalize">{rg.name}</span>
                    <span className={`px-1.5 py-0.5 rounded border text-[10px] ${statusColor(rg.current_regime || 'Baseline')}`}>
                      {rg.current_regime || 'Baseline'}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h4 className="text-sm font-semibold text-white mb-2">12-Week Risk Trend</h4>
              {temporalQuery.isLoading && <LoadingSpinner />}
              <div className="flex items-end gap-1 h-24">
                {snapshots.map((s) => (
                  <div key={s.timestamp} className="flex-1 flex flex-col items-center gap-1">
                    <div
                      className="w-full bg-risk-green rounded-sm transition-all"
                      style={{ height: `${Math.max((s.avg_risk / 100) * 80, 4)}px`, opacity: 0.8 }}
                      title={`avg risk ${s.avg_risk.toFixed(0)}`}
                    />
                    <span className="text-[8px] text-text-muted">
                      {new Date(s.timestamp).toLocaleDateString('en', { month: 'short', day: 'numeric' })}
                    </span>
                  </div>
                ))}
              </div>
              {snapshots.length === 0 && <p className="text-xs text-text-muted mt-2">No snapshots yet</p>}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Diagnostic panel */}
      <Card className="border-border/50 bg-[#12172B]">
        <CardHeader>
          <CardTitle className="text-white text-lg">Diagnostic — Causal Drivers</CardTitle>
          <CardDescription className="text-text-muted">VARLiNGAM causal edges explaining why risk is elevated</CardDescription>
        </CardHeader>
        <CardContent>
          {causalQuery.isLoading && <LoadingSpinner />}
          <div className="space-y-1.5">
            {(causalEdges || []).slice(0, 10).map((e, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className="text-text-secondary">{e.source_variable}</span>
                <span className="text-purple-400">→</span>
                <span className="text-text-secondary">{e.target_variable}</span>
                <div className="flex-1 h-1 bg-gray-700 rounded-full overflow-hidden">
                  <div className="h-full bg-purple-500" style={{ width: `${Math.min(Math.abs(e.weight || 0) * 100, 100)}%` }} />
                </div>
                <span className="text-text-muted w-16 text-right">
                  w={e.weight?.toFixed(2)} · lag {e.lag_weeks || 0}w
                </span>
              </div>
            ))}
            {(causalEdges || []).length === 0 && <p className="text-xs text-text-muted">Run VARLiNGAM discovery to populate causal edges.</p>}
          </div>
        </CardContent>
      </Card>

      {/* Predictive panel */}
      <Card className="border-border/50 bg-[#12172B]">
        <CardHeader>
          <CardTitle className="text-white text-lg">Predictive — Model Consensus Forecast</CardTitle>
          <CardDescription className="text-text-muted">LSTM + XGBoost + SDE + BMA for a region</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-3">
            <select
              value={selectedRegion}
              onChange={(e) => setSelectedRegion(e.target.value)}
              className="bg-[#0A0F1E] border border-border/50 rounded px-3 py-2 text-white text-sm"
            >
              {REGIONS.map((r) => (
                <option key={r} value={r}>{r.replace('_', ' ')}</option>
              ))}
            </select>
            <button
              onClick={async () => { setLoadingForecast(true); try { await loadForecast() } finally { setLoadingForecast(false) } }}
              disabled={loadingForecast}
              className="px-3 py-2 text-xs bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded hover:bg-amber-500/30 transition-colors"
            >
              {loadingForecast ? 'Loading...' : 'Show Consensus'}
            </button>
          </div>

                          {forecastData && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-3 rounded bg-[#0A0F1E] border border-border/50">
                <div className="text-xs text-text-muted mb-1 flex items-center gap-1">
                  LSTM · IPC Phase
                  <div className="group relative">
                    <Info className="h-3 w-3 cursor-help text-text-muted" />
                    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden w-56 rounded-lg bg-gray-900 p-2 text-xs text-gray-300 shadow-xl group-hover:block z-50">
                      Bidirectional LSTM ensemble predicts the most likely IPC phase (1=Minimal to 5=Famine).
                      Confidence reflects model agreement across the 5-model ensemble.
                      Phase ≥4 indicates crisis-level food insecurity.
                    </div>
                  </div>
                </div>
                <div className="text-xl font-bold text-amber-400">{forecastData.lstm?.predicted_phase ?? '—'}</div>
                <div className="text-[10px] text-text-muted">
                  conf {forecastData.lstm?.confidence != null ? (forecastData.lstm.confidence * 100).toFixed(0) + '%' : '—'}
                  {forecastData.lstm?.predicted_phase != null && forecastData.lstm.predicted_phase >= 4 && (
                    <span className="ml-1 text-risk-red font-semibold">⚠ Crisis</span>
                  )}
                </div>
              </div>
              <div className="p-3 rounded bg-[#0A0F1E] border border-border/50">
                <div className="text-xs text-text-muted mb-1 flex items-center gap-1">
                  XGBoost · P(Crisis)
                  <div className="group relative">
                    <Info className="h-3 w-3 cursor-help text-text-muted" />
                    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden w-56 rounded-lg bg-gray-900 p-2 text-xs text-gray-300 shadow-xl group-hover:block z-50">
                      XGBoost binary classifier: probability of IPC Phase ≥3 (Crisis) within 8 weeks.
                      Calibrated with Platt scaling. SHAP values explain top drivers.
                    </div>
                  </div>
                </div>
                <div className="text-xl font-bold text-red-400">{forecastData.xgboost?.p_crisis != null ? (forecastData.xgboost.p_crisis * 100).toFixed(0) + '%' : '—'}</div>
                <div className="text-[10px] text-text-muted">
                  {forecastData.xgboost?.p_crisis != null && forecastData.xgboost.p_crisis > 0.5 && (
                    <span className="text-risk-red font-semibold">High crisis risk</span>
                  )}
                  {forecastData.xgboost?.p_crisis != null && forecastData.xgboost.p_crisis <= 0.5 && forecastData.xgboost.p_crisis > 0.3 && (
                    <span className="text-risk-amber font-semibold">Moderate risk</span>
                  )}
                  {forecastData.xgboost?.p_crisis != null && forecastData.xgboost.p_crisis <= 0.3 && (
                    <span className="text-risk-green font-semibold">Low risk</span>
                  )}
                </div>
              </div>
              <div className="p-3 rounded bg-[#0A0F1E] border border-border/50">
                <div className="text-xs text-text-muted mb-1 flex items-center gap-1">
                  SDE · 4w Drought
                  <div className="group relative">
                    <Info className="h-3 w-3 cursor-help text-text-muted" />
                    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden w-56 rounded-lg bg-gray-900 p-2 text-xs text-gray-300 shadow-xl group-hover:block z-50">
                      CIR jump-diffusion stochastic model: probability of drought (SPI &lt; -1.0) in the next 4 weeks.
                      10,000 Monte Carlo paths. Higher values indicate greater drought risk from rainfall anomalies.
                    </div>
                  </div>
                </div>
                <div className="text-xl font-bold text-blue-400">{forecastData.sde?.p_drought != null ? (forecastData.sde.p_drought * 100).toFixed(0) + '%' : '—'}</div>
                <div className="text-[10px] text-text-muted">
                  {forecastData.sde?.p_drought != null && forecastData.sde.p_drought > 0.5 && (
                    <span className="text-risk-red font-semibold">Elevated drought risk</span>
                  )}
                  {forecastData.sde?.p_drought != null && forecastData.sde.p_drought <= 0.5 && (
                    <span className="text-risk-green font-semibold">Normal range</span>
                  )}
                </div>
              </div>
              <div className="p-3 rounded bg-[#0A0F1E] border border-border/50">
                <div className="text-xs text-text-muted mb-1 flex items-center gap-1">
                  BMA · Posterior
                  <div className="group relative">
                    <Info className="h-3 w-3 cursor-help text-text-muted" />
                    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden w-56 rounded-lg bg-gray-900 p-2 text-xs text-gray-300 shadow-xl group-hover:block z-50">
                      Bayesian Model Averaging posterior risk score combining all 8 models (SDE, HMM, LSTM, XGBoost, CNN, TimeGPT, PageRank, VARLiNGAM).
                      Weighted by recent Brier scores. Range 0–100. Scores ≥60 trigger alerts.
                    </div>
                  </div>
                </div>
                <div className="text-xl font-bold text-risk-green">{forecastData.bma?.score != null ? forecastData.bma.score.toFixed(0) : '—'}</div>
                <div className="text-[10px] text-text-muted">
                  {forecastData.bma?.score != null && forecastData.bma.score >= 60 && (
                    <span className="text-risk-red font-semibold">⚠ Alert threshold</span>
                  )}
                  {forecastData.bma?.score != null && forecastData.bma.score < 60 && forecastData.bma.score >= 30 && (
                    <span className="text-risk-amber font-semibold">Elevated</span>
                  )}
                  {forecastData.bma?.score != null && forecastData.bma.score < 30 && (
                    <span className="text-risk-green font-semibold">Normal</span>
                  )}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Prescriptive panel */}
      <Card className="border-border/50 bg-[#12172B]">
        <CardHeader>
          <CardTitle className="text-white text-lg">Prescriptive — Recommended Actions</CardTitle>
          <CardDescription className="text-text-muted">GNN-PPO policy: what should be done, where</CardDescription>
        </CardHeader>
        <CardContent>
          {policyQuery.isLoading && <LoadingSpinner />}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {recommendations.slice(0, 9).map((rec) => (
              <div key={rec.region_id} className="p-3 rounded bg-[#0A0F1E] border border-border/50">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-semibold text-white capitalize">{rec.region_id.replace('_', ' ')}</span>
                      <span className={`px-1.5 py-0.5 rounded text-[10px] border ${
                        rec.action_label === 'HIGH_ESCALATE' ? 'text-red-400 border-red-500/30 bg-red-500/10'
                          : rec.action_label === 'MEDIUM_SMS' ? 'text-amber-400 border-amber-500/30 bg-amber-500/10'
                          : rec.action_label === 'LOW_ADVISORY' ? 'text-blue-400 border-blue-500/30 bg-blue-500/10'
                          : 'text-gray-400 border-gray-500/30 bg-gray-500/10'
                      }`}>
                        {rec.action_label.replace('_', ' ')}
                      </span>
                      <div className="group relative inline-block">
                        <Info className="h-3 w-3 cursor-help text-text-muted" />
                        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden w-56 rounded-lg bg-gray-900 p-2 text-xs text-gray-300 shadow-xl group-hover:block z-50">
                          {rec.action_label === 'HIGH_ESCALATE' && 'Immediate escalation required. High risk + high confidence. Dispatch SMS alert to affected region immediately.'}
                          {rec.action_label === 'MEDIUM_SMS' && 'Advisory recommended. Moderate risk or moderate confidence. Send SMS advisory to region.'}
                          {rec.action_label === 'LOW_ADVISORY' && 'Low-level advisory. Monitor situation. No immediate action required.'}
                          {rec.action_label === 'NO_ALERT' && 'No alert needed. Risk is low and confidence is sufficient to hold.'}
                        </div>
                      </div>
                    </div>
                <div className="text-[10px] text-text-muted mb-1">confidence {(rec.probability * 100).toFixed(0)}%</div>
                <p className="text-xs text-text-secondary line-clamp-2">{rec.reasoning}</p>
              </div>
            ))}
          </div>
          {recommendations.length === 0 && <p className="text-xs text-text-muted">Train the PPO policy to see recommendations.</p>}
        </CardContent>
      </Card>

      {/* Job history */}
      <Card className="border-border/50 bg-[#12172B]">
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-white text-lg">Job History</CardTitle>
            <CardDescription className="text-text-muted">
              {runningCount > 0 && <span className="text-amber-400 mr-2">● {runningCount} running</span>}
              {failedCount > 0 && <span className="text-red-400">{failedCount} failed (last 20)</span>}
            </CardDescription>
          </div>
          <button
            onClick={() => jobsQuery.refetch()}
            className="px-2 py-1 text-xs text-blue-400 border border-blue-500/30 rounded hover:bg-blue-500/10"
          >
            Refresh
          </button>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-text-secondary">
                <th className="text-left py-2 px-2 font-medium">Job</th>
                <th className="text-left py-2 px-2 font-medium">Status</th>
                <th className="text-right py-2 px-2 font-medium">Records</th>
                <th className="text-right py-2 px-2 font-medium">Duration (s)</th>
                <th className="text-right py-2 px-2 font-medium">Finished</th>
              </tr>
            </thead>
            <tbody>
              {jobs.slice(0, 15).map((j: JobRunRecord) => (
                <tr key={j.id} className="border-b border-border/50">
                  <td className="py-2 px-2 text-white capitalize">{j.job_name.replace('_', ' ')}</td>
                  <td className="py-2 px-2">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] border ${statusColor(j.status)}`}>
                      {fmtStatus(j.status)}
                    </span>
                    <div className="group relative inline-block">
                      <Info className="h-3 w-3 cursor-help text-text-muted ml-1" />
                      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden w-48 rounded-lg bg-gray-900 p-2 text-xs text-gray-300 shadow-xl group-hover:block z-50">
                        {j.status === 'completed' && 'Job finished successfully. All records processed.'}
                        {j.status === 'running' && 'Job is currently executing. Wait for completion.'}
                        {j.status === 'failed' && 'Job failed. Check error message for details.'}
                        {j.status === 'queued' && 'Job is queued and waiting to start.'}
                      </div>
                    </div>
                    {j.error_message && <span title={j.error_message} className="ml-1 text-red-400 cursor-help">⚠</span>}
                  </td>
                  <td className="py-2 px-2 text-right text-text-secondary">{j.records_processed ?? '—'}</td>
                  <td className="py-2 px-2 text-right text-text-secondary">{j.duration_seconds ?? '—'}</td>
                  <td className="py-2 px-2 text-right text-text-muted">{timeAgo(j.finished_at)}</td>
                </tr>
              ))}
              {jobs.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-4 text-center text-xs text-text-muted">No runs yet — trigger a pipeline or model above.</td>
                </tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* Model registry grid */}
      <Card className="border-border/50 bg-[#12172B]">
        <CardHeader>
          <CardTitle className="text-white text-lg">Model Registry</CardTitle>
          <CardDescription className="text-text-muted">All runnable models grouped by layer — click Run to execute</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {LAYER_ORDER.filter((l) => byLayer.has(l)).map((layer) => (
            <div key={layer}>
              <h4 className={`text-xs font-semibold mb-2 ${LAYER_COLORS[layer] || 'text-gray-400'}`}>{layer}</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                {byLayer.get(layer)!.map((m) => (
                  <div key={m.name} className="flex items-center justify-between p-2 rounded bg-[#0A0F1E] border border-border/50">
                    <div className="min-w-0">
                      <div className="text-xs font-medium text-white truncate">{m.label}</div>
                      <div className="text-[10px] text-text-muted">
                        {m.last_status === 'never_run' ? 'never run' : `last ${timeAgo(m.last_finished_at)}`}
                      </div>
                    </div>
                      <div className="flex items-center gap-1.5">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] border ${statusColor(m.last_status)}`}>
                        {fmtStatus(m.last_status)}
                      </span>
                      <div className="group relative">
                        <Info className="h-3 w-3 cursor-help text-text-muted" />
                        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden w-56 rounded-lg bg-gray-900 p-2 text-xs text-gray-300 shadow-xl group-hover:block z-50">
                          {m.last_status === 'never_run' && 'This model has not been executed yet. Run it to generate predictions.'}
                          {m.last_status === 'completed' && 'Last run completed successfully. Predictions are current.'}
                          {m.last_status === 'running' && 'Currently executing. Results will be available shortly.'}
                          {m.last_status === 'failed' && 'Last run failed. Check job history for error details.'}
                        </div>
                      </div>
                      <button
                        onClick={() => runModelMutation.mutate(m.name)}
                        disabled={runModelMutation.isPending}
                        className="px-2 py-1 rounded text-[10px] bg-risk-green/20 text-risk-green border border-risk-green/30 hover:bg-risk-green/30 transition-colors"
                      >
                        Run
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}