import { useQuery } from '@tanstack/react-query'
import { fetchRiskScores } from '@/lib/api'

export function useRiskScores() {
  return useQuery({
    queryKey: ['risk-scores'],
    queryFn: fetchRiskScores,
    refetchInterval: 5 * 60 * 1000,
    staleTime: 4 * 60 * 1000,
  })
}