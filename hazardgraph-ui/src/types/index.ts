export interface RegionRiskScore {
  id: string
  name: string
  country: string
  score: number
  bma_posterior: number
  kelly_priority: number
  confidence: 'High' | 'Medium' | 'Low'
  delta: number
  alert_triggered: boolean
  current_regime: string
  components: {
    rainfall: number
    food: number
    ipc: number
    sde: number
    network: number
  }
  vulnerability_multiplier: number
  model_weights?: Record<string, number>
  component_probabilities?: Record<string, number>
}

export interface RiskScoresResponse {
  computed_at: string
  regions: RegionRiskScore[]
  summary: {
    regions_in_alert: number
    highest_risk_region: string
    average_score: number
  }
}

export interface RegionHistory {
  region_id: string
  history: Array<{ date: string; score: number; regime: string }>
}

export interface GraphNode {
  id: string
  label: string
  type: string
  properties: Record<string, unknown>
}

export interface GraphEdge {
  source: string
  target: string
  type: string
  weight?: number
  lag_days?: number
}

export interface RegimeInfo {
  id: string
  name: string
  region_id: string
  posterior: number
}

export interface LSTMForecast {
  region_id: string
  model: string
  predicted_phase: number
  confidence: number
  model_agreement: number
  probabilities: string
  created_at: string
}

export interface XGBForecast {
  region_id: string
  model: string
  p_crisis: number
  raw_probability: number
  top_shap_features: string
  prediction_date: string
  created_at: string
}

export interface AllForecasts {
  region_id: string
  lstm: { predicted_phase: number; confidence: number } | null
  xgboost: { p_crisis: number } | null
  sde: { p_drought: number; p_flood: number } | null
  bma: { score: number } | null
}
