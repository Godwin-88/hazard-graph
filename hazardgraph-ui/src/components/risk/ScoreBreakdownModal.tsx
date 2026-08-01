import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { TrendingUp, TrendingDown, X, AlertTriangle, Zap, Loader2, Info } from 'lucide-react'
import {
  PieChart, Pie, Cell, ResponsiveContainer,
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine,
  BarChart, Bar,
} from 'recharts'
import { cn } from '@/lib/utils'
import { RegimeBadge } from '@/components/shared/RegimeBadge'
import { ForecastChart } from '@/components/forecast/ForecastChart'
import { runCascadeSimulation } from '@/lib/api'
import type { RegionRiskScore, RegionHistory } from '@/types'
import type { AllForecasts, CascadeResult } from '@/types'

interface ScoreBreakdownModalProps {
  region: RegionRiskScore | null
  history: RegionHistory | null
  onClose: () => void
}

const componentColors: Record<string, string> = {
  rainfall: '#3B82F6',
  food: '#F97316',
  ipc: '#EF4444',
  sde: '#8B5CF6',
  network: '#6B7280',
}

const componentWeights: Record<string, number> = {
  rainfall: 0.30,
  food: 0.20,
  ipc: 0.25,
  sde: 0.15,
  network: 0.10,
}

function getScoreColor(score: number): string {
  if (score < 30) return 'text-risk-green'
  if (score < 60) return 'text-risk-amber'
  return 'text-risk-red'
}

export function ScoreBreakdownModal({ region, history, onClose }: ScoreBreakdownModalProps) {
  const [showCascade, setShowCascade] = useState(false)
  const [cascadeResult, setCascadeResult] = useState<CascadeResult | null>(null)
  const [forecastData, setForecastData] = useState<AllForecasts | null>(null)
  const [forecastLoading, setForecastLoading] = useState(false)

  const cascadeMutation = useMutation({
    mutationFn: () =>
      runCascadeSimulation(region!.id, 8, 500),
    onSuccess: (data) => {
      setCascadeResult(data)
      setShowCascade(true)
    },
  })

  const fetchForecast = async () => {
    if (!region) return
    setForecastLoading(true)
    try {
      const res = await fetch(`/api/v1/forecast/all/${region.id}`, {
        headers: { Authorization: `Bearer ${sessionStorage.getItem('access_token') || ''}` },
      })
      if (res.ok) {
        const data: AllForecasts = await res.json()
        setForecastData(data)
      }
    } catch {
      // Forecast not available
    } finally {
      setForecastLoading(false)
    }
  }

  const pieData = region
    ? Object.entries(region.components).map(([key, value]) => ({
        name: key.charAt(0).toUpperCase() + key.slice(1),
        value: componentWeights[key] * 100,
        fill: componentColors[key],
        opacity: Math.max(0.3, value),
        riskValue: value,
      }))
    : []

  const historyData = history?.history.map((h) => ({
    date: new Date(h.date).toLocaleDateString('en-KE', { month: 'short', day: 'numeric' }),
    score: h.score,
    regime: h.regime,
  })) || []

  const regimeDots = historyData.map((d) => {
    const regimeColors: Record<string, string> = {
      Baseline: '#6B7280',
      DroughtOnset: '#D97706',
      SevereDrought: '#DC2626',
      FloodWatch: '#2563EB',
      FloodEmergency: '#7C3AED',
    }
    return {
      ...d,
      fill: regimeColors[d.regime] || '#6B7280',
    }
  })

  const modelWeightData = region?.model_weights
    ? Object.entries(region.model_weights).map(([name, weight]) => ({
        name,
        weight: typeof weight === 'number' ? weight : 0,
      }))
    : []

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose()
  }

  if (!region) return null

  return (
    <div
      ref={undefined}
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={handleOverlayClick}
    >
      <div className="mx-4 max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-xl border border-border bg-surface p-6 shadow-2xl">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h2
              className="text-2xl font-bold text-text-primary"
              style={{ fontFamily: 'Raleway, sans-serif', fontWeight: 700 }}
            >
              {region.name}
            </h2>
            <RegimeBadge regime={region.current_regime} />
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-text-muted hover:bg-surface-elevated hover:text-text-primary transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Score big number */}
        <div className="mb-6 text-center">
          <span
            className={cn(
              'text-5xl font-bold',
              getScoreColor(region.score),
              region.alert_triggered && region.score >= 60 && 'animate-pulse',
            )}
            style={{ fontFamily: 'Raleway, sans-serif', fontWeight: 800 }}
          >
            {region.score.toFixed(0)}
          </span>
          <span className="ml-2 text-lg text-text-muted">/ 100</span>
          {region.alert_triggered && (
            <div className="mt-2 flex items-center justify-center gap-1 text-risk-red">
              <AlertTriangle className="h-4 w-4" />
              <span className="text-sm font-medium">Alert Triggered</span>
            </div>
          )}
        </div>

        {/* Action buttons */}
        <div className="mb-6 flex gap-3">
          <button
            onClick={fetchForecast}
            disabled={forecastLoading}
            className="flex items-center gap-2 rounded-lg bg-quantifaya-blue/20 px-4 py-2 text-sm text-quantifaya-blue hover:bg-quantifaya-blue/30 transition-colors disabled:opacity-50"
          >
            {forecastLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <TrendingUp className="h-4 w-4" />
            )}
            {forecastData ? 'Refresh Forecast' : 'Load Forecast'}
          </button>
          <button
            onClick={() => cascadeMutation.mutate()}
            disabled={cascadeMutation.isPending}
            className="flex items-center gap-2 rounded-lg bg-quantifaya-green/20 px-4 py-2 text-sm text-quantifaya-green hover:bg-quantifaya-green/30 transition-colors disabled:opacity-50"
          >
            {cascadeMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Zap className="h-4 w-4" />
            )}
            Run Cascade
          </button>
        </div>

        {/* Forecast Chart */}
        {forecastData && (
          <div className="mb-6 rounded-lg border border-border bg-surface-elevated p-4">
            <ForecastChart data={forecastData} regionName={region.name} />
          </div>
        )}

        {/* Cascade Results */}
        {showCascade && cascadeResult && (
          <div className="mb-6 rounded-lg border border-border bg-surface-elevated p-4">
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-text-secondary">
              Contagion Cascade Results
            </h3>
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <span className="text-text-muted">Critical Node</span>
                <p className="text-white font-medium capitalize">
                  {cascadeResult.critical_intervention_node.replace(/_/g, ' ')}
                </p>
              </div>
              <div>
                <span className="text-text-muted">Expected Affected</span>
                <p className="text-white font-medium">
                  {cascadeResult.expected_affected_population_millions.toFixed(1)}M
                </p>
              </div>
              <div>
                <span className="text-text-muted">Simulation Paths</span>
                <p className="text-white font-medium">
                  {cascadeResult.simulation_paths.toLocaleString()}
                </p>
              </div>
            </div>
            <div className="mt-3">
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
                Cascade Probabilities by Region
              </h4>
              <div className="flex flex-wrap gap-2">
                {Object.entries(cascadeResult.cascade_probabilities)
                  .sort(([, a], [, b]) => b - a)
                  .slice(0, 10)
                  .map(([regionId, prob]) => (
                    <div
                      key={regionId}
                      className="rounded bg-surface px-2 py-1 text-xs"
                    >
                      <span className="text-text-secondary">
                        {regionId.replace(/_/g, ' ')}
                      </span>
                      <span className={`ml-1 font-medium ${
                        prob > 0.5 ? 'text-risk-red' : prob > 0.3 ? 'text-risk-amber' : 'text-text-muted'
                      }`}>
                        {(prob * 100).toFixed(0)}%
                      </span>
                    </div>
                  ))}
              </div>
            </div>
          </div>
        )}

        {/* Section 1: Score Breakdown Pie */}
        <div className="mb-6">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-text-secondary">
            Score Breakdown
          </h3>
          <div className="flex items-center justify-center">
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  dataKey="value"
                  startAngle={90}
                  endAngle={-270}
                >
                  {pieData.map((entry, index) => (
                    <Cell
                      key={index}
                      fill={entry.fill}
                      opacity={entry.opacity}
                      stroke={entry.fill}
                      strokeWidth={1}
                    />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1F2937',
                    border: '1px solid #374151',
                    borderRadius: '8px',
                    color: '#F9FAFB',
                  }}
                  formatter={(value: number, name: string) => [
                    `${(value).toFixed(0)}% weight`,
                    name,
                  ]}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex flex-wrap justify-center gap-3">
            {pieData.map((entry) => (
              <div key={entry.name} className="flex items-center gap-1.5">
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: entry.fill, opacity: entry.opacity }}
                />
                <span className="text-xs text-text-secondary">
                  {entry.name} ({(entry.riskValue * 100).toFixed(0)}%)
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Section 2: Historical Trend */}
        {historyData.length > 0 && (
          <div className="mb-6">
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-text-secondary">
              Historical Trend (12 weeks)
            </h3>
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={historyData}>
                <defs>
                  <linearGradient id="scoreGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#EF4444" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#EF4444" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis
                  dataKey="date"
                  tick={{ fill: '#9CA3AF', fontSize: 10 }}
                  axisLine={{ stroke: '#374151' }}
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fill: '#9CA3AF', fontSize: 10 }}
                  axisLine={{ stroke: '#374151' }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1F2937',
                    border: '1px solid #374151',
                    borderRadius: '8px',
                    color: '#F9FAFB',
                  }}
                />
                <ReferenceLine
                  y={60}
                  stroke="#EF4444"
                  strokeDasharray="5 5"
                  label={{
                    value: 'Alert Threshold',
                    fill: '#EF4444',
                    fontSize: 10,
                    position: 'right',
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="score"
                  stroke="#EF4444"
                  fill="url(#scoreGradient)"
                  strokeWidth={2}
                  dot={{ r: 4, fill: '#EF4444' }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Section 3: Model Weights */}
        {modelWeightData.length > 0 && (
          <div className="mb-6">
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-text-secondary">
              BMA Model Weights
            </h3>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart
                data={modelWeightData}
                layout="vertical"
                margin={{ left: 80, right: 20, top: 5, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis
                  type="number"
                  domain={[0, 1]}
                  tick={{ fill: '#9CA3AF', fontSize: 10 }}
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  tick={{ fill: '#9CA3AF', fontSize: 10 }}
                  width={80}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1F2937',
                    border: '1px solid #374151',
                    borderRadius: '8px',
                    color: '#F9FAFB',
                  }}
                  formatter={(value: number) => [(value * 100).toFixed(1) + '%', 'Weight']}
                />
                <Bar dataKey="weight" fill="#0F4C81" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Footer: Metadata */}
        <div className="border-t border-border pt-4">
          {/* VM */}
          <div className="mb-3 flex items-center justify-between text-sm">
            <div className="flex items-center gap-2 text-text-muted">
              <span className="font-medium">VM</span>
              <span className="text-xs">(Vulnerability Multiplier)</span>
              <div className="group relative">
                <Info className="h-3.5 w-3.5 cursor-help text-text-muted" />
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden w-64 rounded-lg bg-gray-900 p-3 text-xs text-gray-300 shadow-xl group-hover:block z-50">
                  Composite index from World Bank/UNDP data.
                  Weights: poverty 40%, road access 25%, pastoral 20%, health 15%.
                  Range 1.0 (low) – 2.5 (critical).
                  Acts as a risk amplifier — higher VM means the same hazard has a larger impact.
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                region.vulnerability_multiplier >= 2.0
                  ? 'bg-risk-red/20 text-risk-red border border-risk-red/30'
                  : region.vulnerability_multiplier >= 1.5
                    ? 'bg-risk-amber/20 text-risk-amber border border-risk-amber/30'
                    : 'bg-risk-green/20 text-risk-green border border-risk-green/30'
              }`}>
                {region.vulnerability_multiplier >= 2.0 ? 'Critical' : region.vulnerability_multiplier >= 1.5 ? 'High' : region.vulnerability_multiplier >= 1.3 ? 'Moderate' : 'Low'}
              </span>
              <span className="font-mono text-text-primary">{region.vulnerability_multiplier.toFixed(3)}</span>
            </div>
          </div>

          {/* Kelly Priority */}
          <div className="mb-3 flex items-center justify-between text-sm">
            <div className="flex items-center gap-2 text-text-muted">
              <span className="font-medium">Kelly Priority</span>
              <span className="text-xs">(Dispatch Score)</span>
              <div className="group relative">
                <Info className="h-3.5 w-3.5 cursor-help text-text-muted" />
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden w-72 rounded-lg bg-gray-900 p-3 text-xs text-gray-300 shadow-xl group-hover:block z-50">
                  Adapted from the Kelly criterion (GraphAlpha f_kelly).
                  Formula: (BMA_risk × confidence) − (1 − BMA_risk) / BMA_risk.
                  Positive → dispatch first (high risk + high confidence).
                  Near zero → dispatch second (moderate).
                  Negative → hold (low risk or low confidence; likely false alarm).
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                region.kelly_priority > 0.3
                  ? 'bg-risk-green/20 text-risk-green border border-risk-green/30'
                  : region.kelly_priority > 0
                    ? 'bg-risk-amber/20 text-risk-amber border border-risk-amber/30'
                    : 'bg-risk-red/20 text-risk-red border border-risk-red/30'
              }`}>
                {region.kelly_priority > 0.3 ? 'Dispatch First' : region.kelly_priority > 0 ? 'Dispatch Second' : 'Hold'}
              </span>
              <span className={`font-mono font-semibold ${
                region.kelly_priority > 0 ? 'text-risk-green' : region.kelly_priority > 0 ? 'text-risk-amber' : 'text-risk-red'
              }`}>
                {region.kelly_priority.toFixed(3)}
              </span>
            </div>
          </div>

          {/* Expandable Detail Section */}
          <details className="group">
            <summary className="cursor-pointer text-xs text-text-muted hover:text-text-primary transition-colors">
              View formula & interpretation
            </summary>
            <div className="mt-2 rounded-lg bg-surface-elevated p-3 text-xs text-text-secondary space-y-2">
              <div>
                <span className="font-medium text-text-primary">Vulnerability Multiplier</span>
                <p className="mt-1">
                  VM = 1.0 + (poverty × 0.40) + ((1 − road_access) × 0.25) + (pastoral × 0.20) + ((1 − health_access) × 0.15)
                </p>
                <p className="mt-0.5 text-text-muted">
                  Applied as a multiplier on the raw BMA risk score. A region with VM=2.0 experiences roughly 2× the impact of the same hazard.
                </p>
              </div>
              <div className="border-t border-border pt-2">
                <span className="font-medium text-text-primary">Kelly Priority</span>
                <p className="mt-1">
                  Kelly = (BMA_risk × confidence) − (1 − BMA_risk) / BMA_risk
                </p>
                <p className="mt-0.5 text-text-muted">
                  Derived from the GraphAlpha f_kelly formula. Positive scores indicate alerts where the expected benefit of dispatch outweighs the cost of false alarms. Negative scores suggest holding the alert pending confirmation.
                </p>
              </div>
            </div>
          </details>
        </div>
      </div>
    </div>
  )
}