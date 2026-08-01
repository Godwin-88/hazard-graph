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
  // BUGFIX: AuthContext stores token in sessionStorage, not localStorage
  const token = sessionStorage.getItem('access_token')
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

export interface CausalEdge {
  id: string
  source_variable: string
  target_variable: string
  weight: number
  lag_weeks: number
  p_value: number
  region_id: string
  method: string
  discovered_at: string
}

export async function fetchCausalEdges(): Promise<CausalEdge[]> {
  return fetchJson<CausalEdge[]>(`${BASE_URL}/api/v1/graph/causal-edges`)
}

export async function triggerScoring(): Promise<RiskScoresResponse> {
  const res = await fetch(`${BASE_URL}/api/v1/risk/trigger-scoring`, {
    method: 'POST',
    headers: getAuthHeaders(),
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

// ── Pipeline / Model Runner ─────────────────────────────

export interface PipelineModel {
  name: string
  label: string
  layer: string
  last_status: string
  last_finished_at: string | null
  last_records: number | null
}

export interface JobRunRecord {
  id: string
  job_name: string
  status: string
  started_at: string | null
  finished_at: string | null
  duration_seconds: number | null
  records_processed: number | null
  error_message: string | null
}

export async function fetchPipelineStatus(): Promise<{ models: PipelineModel[] }> {
  return fetchJson<{ models: PipelineModel[] }>(`${BASE_URL}/api/v1/pipeline/status`)
}

export async function fetchJobHistory(): Promise<{ jobs: JobRunRecord[] }> {
  return fetchJson<{ jobs: JobRunRecord[] }>(`${BASE_URL}/api/v1/pipeline/jobs`)
}

export async function runPipelineScope(
  scope: 'full' | 'scoring' | 'models',
  models?: string[],
): Promise<{ run_id: string; status: string; scope?: string; message?: string; runs?: { model: string; run_id: string; label: string }[] }> {
  const res = await fetch(`${BASE_URL}/api/v1/pipeline/run`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(models ? { scope, models } : { scope }),
  })
  if (!res.ok) throw new Error(`Pipeline run failed: ${res.status}`)
  return res.json()
}

export async function runSingleModel(
  name: string,
): Promise<{ run_id: string; status: string; model: string; label: string }> {
  const res = await fetch(`${BASE_URL}/api/v1/pipeline/models/${name}`, {
    method: 'POST',
    headers: getAuthHeaders(),
  })
  if (!res.ok) throw new Error(`Model run failed: ${res.status}`)
  return res.json()
}

export async function sendAssistantMessage(
  message: string,
  context?: string,
): Promise<{ reply: string }> {
  const res = await fetch(`${BASE_URL}/api/v1/assistant/chat`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ message, context }),
  })
  if (!res.ok) throw new Error(`Assistant request failed: ${res.status}`)
  return res.json()
}
