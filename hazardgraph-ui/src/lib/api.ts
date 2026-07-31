import type {
  RiskScoresResponse,
  RegionRiskScore,
  RegionHistory,
  GraphNode,
  GraphEdge,
  RegimeInfo,
  LSTMForecast,
  AllForecasts,
  PolicyResponse,
  CascadeResult,
  HazardCluster,
  TemporalSnapshot,
} from '@/types'

const BASE_URL = ''

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('access_token')
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: getAuthHeaders() })
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

export async function fetchPolicyRecommendations(): Promise<PolicyResponse> {
  return fetchJson<PolicyResponse>(`${BASE_URL}/api/v1/rl/recommendations`)
}

export async function triggerPolicyTraining(): Promise<{ status: string; message: string }> {
  const res = await fetch(`${BASE_URL}/api/v1/rl/train`, {
    method: 'POST',
    headers: getAuthHeaders(),
  })
  if (!res.ok) throw new Error(`Training trigger failed: ${res.status}`)
  return res.json()
}

export async function runCascadeSimulation(
  sourceRegion: string,
  horizonWeeks: number = 8,
  nPaths: number = 500,
): Promise<CascadeResult> {
  const res = await fetch(`${BASE_URL}/api/v1/scenarios/cascade`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({
      source_region: sourceRegion,
      horizon_weeks: horizonWeeks,
      n_paths: nPaths,
    }),
  })
  if (!res.ok) throw new Error(`Cascade failed: ${res.status}`)
  return res.json()
}

export async function fetchHazardClusters(): Promise<{ clusters: HazardCluster[] }> {
  return fetchJson<{ clusters: HazardCluster[] }>(`${BASE_URL}/api/v1/scenarios/clusters`)
}

export async function refreshClusters(): Promise<{ status: string; cluster_count: number; clusters: HazardCluster[] }> {
  const res = await fetch(`${BASE_URL}/api/v1/scenarios/clusters/refresh`, {
    method: 'POST',
    headers: getAuthHeaders(),
  })
  if (!res.ok) throw new Error(`Cluster refresh failed: ${res.status}`)
  return res.json()
}

export async function fetchTemporalGraph(): Promise<{ snapshots: TemporalSnapshot[] }> {
  return fetchJson<{ snapshots: TemporalSnapshot[] }>(`${BASE_URL}/api/v1/scenarios/temporal-graph`)
}
