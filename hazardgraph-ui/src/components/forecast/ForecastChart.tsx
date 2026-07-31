import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Legend,
} from 'recharts'
import type { AllForecasts } from '@/types'

interface ForecastChartProps {
  data: AllForecasts
  regionName: string
}

function formatForecastValue(
  value: number | null,
  field: string,
): string {
  if (value === null || value === undefined) return 'N/A'
  if (field === 'predicted_phase') return `IPC ${value}`
  if (field === 'p_crisis') return `${(value * 100).toFixed(1)}%`
  if (field === 'p_drought') return `${(value * 100).toFixed(1)}%`
  if (field === 'p_flood') return `${(value * 100).toFixed(1)}%`
  if (field === 'score') return value.toFixed(1)
  return String(value)
}

export function ForecastChart({ data, regionName }: ForecastChartProps) {
  const lstm = data.lstm
  const xgb = data.xgboost
  const sde = data.sde
  const bma = data.bma

  const chartData = [
    {
      week: 'W1',
      lstm: lstm?.predicted_phase ?? null,
      xgb: xgb?.p_crisis ?? null,
      sde_drought: sde?.p_drought ?? null,
      sde_flood: sde?.p_flood ?? null,
      bma: bma?.score ?? null,
    },
    {
      week: 'W2',
      lstm: lstm?.predicted_phase ?? null,
      xgb: xgb?.p_crisis ?? null,
      sde_drought: sde?.p_drought ?? null,
      sde_flood: sde?.p_flood ?? null,
      bma: bma?.score ?? null,
    },
    {
      week: 'W3',
      lstm: lstm?.predicted_phase ?? null,
      xgb: xgb?.p_crisis ?? null,
      sde_drought: sde?.p_drought ?? null,
      sde_flood: sde?.p_flood ?? null,
      bma: bma?.score ?? null,
    },
    {
      week: 'W4',
      lstm: lstm?.predicted_phase ?? null,
      xgb: xgb?.p_crisis ?? null,
      sde_drought: sde?.p_drought ?? null,
      sde_flood: sde?.p_flood ?? null,
      bma: bma?.score ?? null,
    },
  ]

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">
        4-Week Forecast — {regionName}
      </h3>

      <div className="flex items-center gap-4 text-xs text-text-muted">
        {lstm && (
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-blue-500" />
            LSTM (IPC phase)
          </span>
        )}
        {xgb && (
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-amber-500" />
            XGBoost (crisis P)
          </span>
        )}
        {sde && (
          <>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              SDE drought P
            </span>
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-cyan-500" />
              SDE flood P
            </span>
          </>
        )}
        {bma && (
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-purple-500" />
            BMA score
          </span>
        )}
      </div>

      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2D3A5C" />
          <XAxis dataKey="week" stroke="#7B8DB8" />
          <YAxis
            stroke="#7B8DB8"
            domain={[0, 1]}
            tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1A2340',
              border: '1px solid #2D3A5C',
              borderRadius: '8px',
              color: '#F9FAFB',
            }}
            formatter={(value: unknown, name: string) => {
              if (value === null || value === undefined) return ['N/A', name]
              return [formatForecastValue(value as number, name), name]
            }}
          />
          <Legend />
          {lstm && (
            <Area
              type="monotone"
              dataKey="lstm"
              stroke="#3B82F6"
              fill="#3B82F6"
              fillOpacity={0.15}
              strokeWidth={2}
              name="LSTM (IPC phase)"
              dot={{ r: 4, fill: '#3B82F6' }}
            />
          )}
          {xgb && (
            <Area
              type="monotone"
              dataKey="xgb"
              stroke="#F59E0B"
              fill="#F59E0B"
              fillOpacity={0.15}
              strokeWidth={2}
              name="XGBoost (crisis P)"
              dot={{ r: 4, fill: '#F59E0B' }}
            />
          )}
          {sde && (
            <Area
              type="monotone"
              dataKey="sde_drought"
              stroke="#10B981"
              fill="#10B981"
              fillOpacity={0.1}
              strokeWidth={1.5}
              name="SDE drought P"
              dot={{ r: 3, fill: '#10B981' }}
            />
          )}
          {sde && (
            <Area
              type="monotone"
              dataKey="sde_flood"
              stroke="#06B6D4"
              fill="#06B6D4"
              fillOpacity={0.1}
              strokeWidth={1.5}
              name="SDE flood P"
              dot={{ r: 3, fill: '#06B6D4' }}
            />
          )}
          {bma && (
            <Area
              type="monotone"
              dataKey="bma"
              stroke="#8B5CF6"
              fill="#8B5CF6"
              fillOpacity={0.1}
              strokeWidth={2}
              name="BMA score"
              dot={{ r: 4, fill: '#8B5CF6' }}
            />
          )}
        </AreaChart>
      </ResponsiveContainer>

      <div className="grid grid-cols-2 gap-3 text-xs">
        {lstm && (
          <div className="rounded bg-surface-elevated p-2">
            <span className="text-text-muted">LSTM Confidence</span>
            <p className="text-white font-medium">
              {(lstm.confidence * 100).toFixed(0)}%
            </p>
          </div>
        )}
        {xgb && (
          <div className="rounded bg-surface-elevated p-2">
            <span className="text-text-muted">XGBoost Crisis P</span>
            <p className="text-white font-medium">
              {(xgb.p_crisis * 100).toFixed(1)}%
            </p>
          </div>
        )}
        {bma && (
          <div className="rounded bg-surface-elevated p-2">
            <span className="text-text-muted">BMA Risk Score</span>
            <p className="text-white font-medium">{bma.score.toFixed(1)}</p>
          </div>
        )}
        {lstm && (
          <div className="rounded bg-surface-elevated p-2">
            <span className="text-text-muted">Model Agreement</span>
            <p className="text-white font-medium">
              {(lstm as { model_agreement?: number }).model_agreement !== undefined
                ? ((lstm as { model_agreement?: number }).model_agreement * 100).toFixed(0) + '%'
                : 'N/A'}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}