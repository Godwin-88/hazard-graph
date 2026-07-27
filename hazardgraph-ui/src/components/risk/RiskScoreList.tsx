import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { useRiskScores } from '@/hooks/useRiskScores'
import { RegionScoreCard } from './RegionScoreCard'
import { ScoreBreakdownModal } from './ScoreBreakdownModal'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import { triggerScoring } from '@/lib/api'
import { useRegionHistory } from '@/hooks/useRegionDetail'
import { useQueryClient } from '@tanstack/react-query'
import type { RegionRiskScore } from '@/types'

export function RiskScoreList() {
  const { data, isLoading, error } = useRiskScores()
  const queryClient = useQueryClient()
  const [selectedRegion, setSelectedRegion] = useState<RegionRiskScore | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const { data: historyData } = useRegionHistory(selectedRegion?.id ?? null)

  const handleRefresh = async () => {
    setIsRefreshing(true)
    try {
      await triggerScoring()
      queryClient.invalidateQueries({ queryKey: ['risk-scores'] })
    } catch (err) {
      console.error('Refresh failed:', err)
    } finally {
      setIsRefreshing(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3">
        {Array.from({ length: 11 }).map((_, i) => (
          <div
            key={i}
            className="h-28 animate-pulse rounded-lg border border-border bg-surface"
          />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-risk-red/30 bg-risk-red/5 p-6 text-center">
        <p className="text-risk-red">Failed to load risk scores</p>
        <p className="text-sm text-text-muted">{(error as Error).message}</p>
        <button
          onClick={() => queryClient.invalidateQueries({ queryKey: ['risk-scores'] })}
          className="rounded bg-surface-elevated px-4 py-2 text-sm text-text-primary hover:bg-border"
        >
          Retry
        </button>
      </div>
    )
  }

  const sortedRegions = [...(data?.regions || [])].sort((a, b) => b.score - a.score)
  const computedAt = data?.computed_at || ''

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <h2
          className="text-lg font-semibold text-text-primary"
          style={{ fontFamily: 'Raleway, sans-serif', fontWeight: 600 }}
        >
          Regional Risk Index
        </h2>
        <button
          onClick={handleRefresh}
          disabled={isRefreshing}
          className="flex items-center gap-1.5 rounded border border-border bg-surface-elevated px-3 py-1.5 text-sm text-text-secondary transition-colors hover:bg-border disabled:opacity-50"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin' : ''}`}
          />
          Refresh
        </button>
      </div>

      {/* Score Cards */}
      <div className="flex-1 space-y-2 overflow-y-auto pr-1">
        {sortedRegions.map((region) => (
          <RegionScoreCard
            key={region.id}
            region={region}
            onClick={() => setSelectedRegion(region)}
          />
        ))}
      </div>

      {/* Modal */}
      <ScoreBreakdownModal
        region={selectedRegion}
        history={historyData ?? null}
        onClose={() => setSelectedRegion(null)}
      />
    </div>
  )
}