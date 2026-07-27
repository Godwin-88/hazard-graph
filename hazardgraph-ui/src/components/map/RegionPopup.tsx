import type { RegionRiskScore } from '@/types'
import { RegimeBadge } from '@/components/shared/RegimeBadge'
import { cn } from '@/lib/utils'

interface RegionPopupProps {
  region: RegionRiskScore
  onViewDetails: () => void
}

function getScoreColor(score: number): string {
  if (score < 30) return 'text-risk-green'
  if (score < 60) return 'text-risk-amber'
  return 'text-risk-red'
}

export function RegionPopup({ region, onViewDetails }: RegionPopupProps) {
  return (
    <div className="min-w-[200px] rounded-lg bg-surface p-3" style={{ fontFamily: 'Raleway, sans-serif' }}>
      <div className="mb-2 flex items-center justify-between">
        <span className="font-semibold text-text-primary">{region.name}</span>
        <RegimeBadge regime={region.current_regime} />
      </div>
      <div className="mb-3 flex items-baseline gap-1">
        <span className={cn('text-2xl font-bold', getScoreColor(region.score))}>
          {region.score.toFixed(0)}
        </span>
        <span className="text-xs text-text-muted">/ 100</span>
      </div>
      {region.alert_triggered && (
        <div className="mb-2 rounded bg-risk-red/20 px-2 py-1 text-xs text-risk-red">
          ⚠ Alert triggered
        </div>
      )}
      <button
        onClick={onViewDetails}
        className="w-full rounded bg-quantifaya-blue px-3 py-1.5 text-sm text-white transition-colors hover:bg-quantifaya-blue/80"
      >
        View Details
      </button>
    </div>
  )
}