import { useQuery } from '@tanstack/react-query'
import { fetchRegionDetail, fetchRegionHistory } from '@/lib/api'

export function useRegionDetail(regionId: string | null) {
  return useQuery({
    queryKey: ['region', regionId],
    queryFn: () => fetchRegionDetail(regionId!),
    enabled: !!regionId,
  })
}

export function useRegionHistory(regionId: string | null) {
  return useQuery({
    queryKey: ['region-history', regionId],
    queryFn: () => fetchRegionHistory(regionId!),
    enabled: !!regionId,
  })
}