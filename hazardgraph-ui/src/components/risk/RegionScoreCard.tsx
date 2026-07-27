import { TrendingUp, TrendingDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { RegimeBadge } from '@/components/shared/RegimeBadge'
import type { RegionRiskScore } from '@/types'

interface RegionScoreCardProps {
  region: RegionRiskScore
  onClick: () => void
}

function getScoreColor(score: number): string {
  if (score < 30) return 'text-risk-green'
  if (score < 60) return 'text-risk-amber'
  return 'text-risk-red'
}

function getConfidenceColor(confidence: string): string {
  switch (confidence) {
    case 'High':
      return 'bg-risk-green/20 text-risk-green'
    case 'Medium':
      return 'bg-risk-amber/20 text-risk-amber'
    case 'Low':
      return 'bg-gray-500/20 text-gray-400'
    default:
      return 'bg-gray-500/20 text-gray-400'
  }
}

const countryFlags: Record<string, string> = {
  ethiopia: '🇪🇹',
  kenya: '🇰🇪',
  somalia: '🇸🇴',
  sudan: '🇸🇩',
  south_sudan: '🇸🇸',
  uganda: '🇺🇬',
  djibouti: '🇩🇯',
  eritrea: '🇪🇷',
  tanzania: '🇹🇿',
  burundi: '🇧🇮',
  rwanda: '🇷🇼',
}

export function RegionScoreCard({ region, onClick }: RegionScoreCardProps) {
  const flag = countryFlags[region.country.toLowerCase()] || '🌍'

  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full rounded-lg border border-border bg-surface p-4 text-left transition-all',
        'hover:border-risk-green/50 hover:bg-surface-elevated',
        'focus:outline-none focus:ring-2 focus:ring-risk-green/50',
      )}
    >
      {/* Top: Name + Flag + Regime */}
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">{flag}</span>
          <span
            className="text-base font-semibold text-text-primary"
            style={{ fontFamily: 'Raleway, sans-serif', fontWeight: 600 }}
          >
            {region.name}
          </span>
        </div>
        <RegimeBadge regime={region.current_regime} />
      </div>

      {/* Centre: Score */}
      <div className="mb-2 flex items-baseline gap-1">
        <span
          className={cn(
            'text-3xl font-bold',
            getScoreColor(region.score),
            region.alert_triggered && region.score >= 60 && 'animate-pulse',
          )}
          style={{ fontFamily: 'Raleway, sans-serif', fontWeight: 700 }}
        >
          {region.score.toFixed(0)}
        </span>
        <span className="text-sm text-text-muted">/ 100</span>
      </div>

      {/* Bottom row: Delta + Confidence */}
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-1">
          {region.delta > 0 ? (
            <TrendingUp className="h-4 w-4 text-risk-red" />
          ) : region.delta < 0 ? (
            <TrendingDown className="h-4 w-4 text-risk-green" />
          ) : null}
          <span
            className={cn(
              'text-sm font-medium',
              region.delta > 0 ? 'text-risk-red' : region.delta < 0 ? 'text-risk-green' : 'text-text-muted',
            )}
          >
            {region.delta > 0 ? '+' : ''}
            {region.delta.toFixed(1)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
              getConfidenceColor(region.confidence),
            )}
          >
            {region.confidence}
          </span>
          <span className="text-xs text-text-muted">
            BMA: {region.bma_posterior.toFixed(2)}
          </span>
        </div>
      </div>

      {/* Kelly priority bar */}
      {region.kelly_priority > 0 && (
        <div className="h-1 w-full overflow-hidden rounded-full bg-border">
          <div
            className={cn(
              'h-full rounded-full transition-all',
              region.kelly_priority > 0.5 ? 'bg-risk-red' : 'bg-risk-amber',
            )}
            style={{ width: `${Math.min(region.kelly_priority * 100, 100)}%` }}
          />
        </div>
      )}
    </button>
  )
}