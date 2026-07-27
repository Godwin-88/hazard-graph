import { useState } from 'react'
import { QuantifayaHeader } from '@/components/layout/QuantifayaHeader'
import { RiskChoropleth } from '@/components/map/RiskChoropleth'
import { RiskScoreList } from '@/components/risk/RiskScoreList'
import { useRiskScores } from '@/hooks/useRiskScores'
import type { RegionRiskScore } from '@/types'

function timeAgo(dateStr: string): string {
  if (!dateStr) return 'never'
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const diffMs = now - then
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  return `${Math.floor(diffHr / 24)}d ago`
}

export function Dashboard() {
  const { data, isLoading } = useRiskScores()
  const [selectedRegion, setSelectedRegion] = useState<RegionRiskScore | null>(null)

  const summary = data?.summary
  const computedAt = data?.computed_at || ''
  const regions = data?.regions || []

  return (
    <div className="flex h-screen flex-col bg-background">
      {/* Row 1: Header */}
      <QuantifayaHeader />

      {/* Row 2: Two-column layout */}
      <div className="flex flex-1 gap-4 overflow-hidden p-4">
        {/* Left: Map */}
        <div className="flex w-[65%] flex-col">
          <RiskChoropleth
            regions={regions}
            onRegionClick={(region) => setSelectedRegion(region)}
          />
          {/* Bottom bar: Summary stats */}
          {summary && (
            <div className="mt-2 flex items-center gap-4 rounded-lg border border-border bg-surface px-4 py-2 text-sm text-text-secondary">
              <span>🔴 <span className="font-medium text-text-primary">{summary.regions_in_alert}</span> regions in alert</span>
              <span className="text-border">|</span>
              <span>⚠️ Highest risk: <span className="font-medium text-text-primary">{summary.highest_risk_region}</span></span>
              <span className="text-border">|</span>
              <span>📊 Avg score: <span className="font-medium text-text-primary">{summary.average_score.toFixed(1)}</span></span>
              <span className="text-border">|</span>
              <span>🕐 Updated: <span className="font-medium text-text-primary">{timeAgo(computedAt)}</span></span>
            </div>
          )}
        </div>

        {/* Right: Score list sidebar */}
        <div className="w-[35%] overflow-hidden">
          <RiskScoreList />
        </div>
      </div>
    </div>
  )
}