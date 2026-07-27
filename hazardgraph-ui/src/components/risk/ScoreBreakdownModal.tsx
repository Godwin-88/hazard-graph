import { useEffect, useRef } from 'react'
import { TrendingUp, TrendingDown, X, AlertTriangle } from 'lucide-react'
import {
  PieChart, Pie, Cell, ResponsiveContainer,
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine,
  BarChart, Bar,
} from 'recharts'
import { cn } from '@/lib/utils'
import { RegimeBadge } from '@/components/shared/RegimeBadge'
import type { RegionRiskScore, RegionHistory } from '@/types'

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
  const overlayRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleEsc)
    return () => document.removeEventListener('keydown', handleEsc)
  }, [onClose])

  if (!region) return null

  const pieData = Object.entries(region.components).map(([key, value]) => ({
    name: key.charAt(0).toUpperCase() + key.slice(1),
    value: componentWeights[key] * 100,
    fill: componentColors[key],
    opacity: Math.max(0.3, value),
    riskValue: value,
  }))

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

  const modelWeightData = region.model_weights
    ? Object.entries(region.model_weights).map(([name, weight]) => ({
        name,
        weight: typeof weight === 'number' ? weight : 0,
      }))
    : []

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === overlayRef.current) onClose()
  }

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={handleOverlayClick}
    >
      <div className="mx-4 max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-border bg-surface p-6 shadow-2xl">
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
        <div className="flex items-center justify-between border-t border-border pt-4 text-sm text-text-muted">
          <div className="flex items-center gap-1 text-text-muted">
            <span className="font-medium">VM:</span>
            <span>{region.vulnerability_multiplier.toFixed(3)}</span>
          </div>
          <div className="flex items-center gap-1 text-text-muted">
            <span className="font-medium">Kelly Priority:</span>
            <span
              className={cn(
                'font-semibold',
                region.kelly_priority > 0.5
                  ? 'text-risk-red'
                  : region.kelly_priority > 0.2
                    ? 'text-risk-amber'
                    : 'text-text-muted',
              )}
            >
              {region.kelly_priority.toFixed(3)}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}