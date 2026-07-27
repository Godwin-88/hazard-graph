import type {
  RiskScoresResponse,
  RegionRiskScore,
  RegionHistory,
  GraphNode,
  GraphEdge,
  RegimeInfo,
  LSTMForecast,
  AllForecasts,
} from '@/types'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${res.statusText}`)
  }
  return res.json()
}

export async function fetchRiskScores(): Promise<RiskScoresResponse> {
  return fetchJson<RiskScoresResponse>(`${BASE_URL}/api/v1/risk/scores`)
}

export async function fetchRegionDetail(
  regionId: string,
): Promise<RegionRiskScore> {
  return fetchJson<RegionRiskScore>(`${BASE_URL}/api/v1/risk/scores/${regionId}`)
}

export async function fetchRegionHistory(
  regionId: string,
): Promise<RegionHistory> {
  return fetchJson<RegionHistory>(`${BASE_URL}/api/v1/risk/history/${regionId}`)
}

export async function fetchGraphNodes(): Promise<{
  nodes: GraphNode[]
  edges: GraphEdge[]
}> {
  return fetchJson<{ nodes: GraphNode[]; edges: GraphEdge[] }>(
    `${BASE_URL}/api/v1/graph/nodes`,
  )
}

export async function fetchRegimes(): Promise<{ regions: RegimeInfo[] }> {
  return fetchJson<{ regions: RegimeInfo[] }>(`${BASE_URL}/api/v1/graph/regimes`)
}

export async function triggerScoring(): Promise<RiskScoresResponse> {
  const res = await fetch(`${BASE_URL}/api/v1/risk/trigger-scoring`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  if (!res.ok) {
    throw new Error(`Trigger failed: ${res.status}`)
  }
  return res.json()
}

export async function fetchLSTMForecast(
  regionId: string,
): Promise<LSTMForecast> {
  return fetchJson<LSTMForecast>(
    `${BASE_URL}/api/v1/forecast/lstm/${regionId}`,
  )
}

export async function fetchAllForecasts(
  regionId: string,
): Promise<AllForecasts> {
  return fetchJson<AllForecasts>(
    `${BASE_URL}/api/v1/forecast/all/${regionId}`,
  )
}
