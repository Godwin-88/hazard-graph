import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { RiskChoropleth } from '@/components/map/RiskChoropleth'
import { RiskScoreList } from '@/components/risk/RiskScoreList'
import { useRiskScores } from '@/hooks/useRiskScores'
import { fetchHazardClusters } from '@/lib/api'
import type { RegionRiskScore } from '@/types'
import type { HazardCluster } from '@/types'

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
  const [showClusters, setShowClusters] = useState(false)

  const { data: clusterData } = useQuery({
    queryKey: ['hazard-clusters'],
    queryFn: fetchHazardClusters,
    refetchInterval: 5 * 60 * 1000,
    staleTime: 4 * 60 * 1000,
  })

  const summary = data?.summary
  const computedAt = data?.computed_at || ''
  const regions = data?.regions || []
  const clusters: HazardCluster[] = clusterData?.clusters || []

  return (
    <div className="flex flex-col bg-background">
      {/* Two-column layout */}
      <div className="flex gap-4 p-4">
        {/* Left: Map */}
        <div className="flex w-[65%] flex-col">
          <div className="h-[calc(100vh-240px)] min-h-[420px]">
            <RiskChoropleth
              regions={regions}
              clusters={showClusters ? clusters : []}
              onRegionClick={(region) => setSelectedRegion(region)}
            />
          </div>
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
          {/* Cluster toggle */}
          <div className="mt-2 flex items-center gap-2">
            <button
              onClick={() => setShowClusters(!showClusters)}
              className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
                showClusters
                  ? 'bg-quantifaya-blue text-white'
                  : 'bg-surface-elevated text-text-secondary border border-border'
              }`}
            >
              {showClusters ? '✓ Clusters' : 'Cluster Overlay'}
            </button>
            {showClusters && clusters.length > 0 && (
              <span className="text-xs text-text-muted">
                {clusters.length} zones active
              </span>
            )}
          </div>
        </div>

        {/* Right: Score list sidebar */}
        <div className="w-[35%] overflow-hidden">
          <RiskScoreList />
        </div>
      </div>
    </div>
  )
}