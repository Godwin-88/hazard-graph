import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import {
  fetchModelHealth,
  fetchPipelineFreshness,
  fetchAlertLineage,
  triggerDatahubSync,
  queryHazardAgent,
  type ModelHealth,
  type FreshnessStatus,
  type AlertLineage,
  type DatahubSyncResult,
  type AgentQueryResult,
} from '@/lib/api'

// ── Helpers ──────────────────────────────────────────────

function getBrierColor(score: number | null): string {
  if (score === null) return 'text-text-secondary'
  if (score < 0.2) return 'text-emerald-400'
  if (score <= 0.25) return 'text-amber-400'
  return 'text-red-400'
}

function getBrierBadge(score: number | null): string {
  if (score === null) return 'bg-gray-500/20 text-text-secondary'
  if (score < 0.2) return 'bg-emerald-500/15 text-emerald-400'
  if (score <= 0.25) return 'bg-amber-500/15 text-amber-400'
  return 'bg-red-500/15 text-red-400'
}

function getFreshnessBadge(status: string): string {
  if (status === 'fresh') return 'bg-emerald-500/15 text-emerald-400'
  if (status === 'stale') return 'bg-red-500/15 text-red-400'
  return 'bg-gray-500/20 text-text-secondary'
}

function formatAge(hours?: number): string {
  if (hours === undefined || hours === null) return '—'
  if (hours < 1) return `${Math.round(hours * 60)}m`
  if (hours < 24) return `${hours.toFixed(1)}h`
  return `${(hours / 24).toFixed(1)}d`
}

const SUGGESTED_QUERIES = [
  'Which models are underperforming this week?',
  'Is the CHIRPS data fresh enough to trust this week\'s forecasts?',
  'What is the contagion risk from Somalia to Ethiopia if BMA exceeds 0.7?',
  'Why was the alert dispatched?',
]

// ── Sub-components ──────────────────────────────────────

function ModelHealthTable({ models }: { models: ModelHealth[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-text-secondary">
            <th className="text-left py-3 px-2 font-medium">ID</th>
            <th className="text-left py-3 px-2 font-medium">Model</th>
            <th className="text-left py-3 px-2 font-medium">Category</th>
            <th className="text-right py-3 px-2 font-medium">Brier</th>
            <th className="text-right py-3 px-2 font-medium">BMA Weight</th>
            <th className="text-left py-3 px-2 font-medium">Update</th>
          </tr>
        </thead>
        <tbody>
          {models.map((m) => (
            <tr key={m.id} className="border-b border-border/50">
              <td className="py-3 px-2 font-mono text-risk-green">{m.id}</td>
              <td className="py-3 px-2">
                <div className="text-white font-medium">{m.name}</div>
                <div className="text-xs text-text-secondary mt-0.5">{m.technique}</div>
              </td>
              <td className="py-3 px-2 text-text-secondary">{m.category}</td>
              <td className="py-3 px-2 text-right">
                <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', getBrierBadge(m.brier_score))}>
                  {m.brier_score !== null ? m.brier_score.toFixed(3) : 'pending'}
                </span>
              </td>
              <td className={cn('py-3 px-2 text-right font-medium', getBrierColor(m.bma_weight ?? null))}>
                {m.bma_weight !== null ? m.bma_weight.toFixed(3) : '—'}
              </td>
              <td className="py-3 px-2 text-xs text-text-secondary">{m.update_frequency}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FreshnessTable({ datasets }: { datasets: Record<string, FreshnessStatus> }) {
  const rows = Object.entries(datasets)
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-text-secondary">
            <th className="text-left py-3 px-2 font-medium">Dataset</th>
            <th className="text-left py-3 px-2 font-medium">Status</th>
            <th className="text-right py-3 px-2 font-medium">Age</th>
            <th className="text-right py-3 px-2 font-medium">Max Age</th>
            <th className="text-left py-3 px-2 font-medium">Last Updated</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, ds]) => (
            <tr key={name} className="border-b border-border/50">
              <td className="py-3 px-2 font-mono text-xs text-white">{name}</td>
              <td className="py-3 px-2">
                <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium uppercase', getFreshnessBadge(ds.status))}>
                  {ds.status}
                </span>
              </td>
              <td className="py-3 px-2 text-right text-text-secondary">{formatAge(ds.age_hours)}</td>
              <td className="py-3 px-2 text-right text-text-secondary">{formatAge(ds.max_age_hours)}</td>
              <td className="py-3 px-2 text-xs text-text-secondary">
                {ds.last_updated ? new Date(ds.last_updated).toLocaleString() : (ds.note ?? '—')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function LineageView({ lineage }: { lineage: AlertLineage }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-text-secondary">
          Provenance chain for alert <span className="font-mono text-risk-green">{lineage.alert_id}</span>
        </p>
        <a
          href={lineage.datahub_lineage_url}
          target="_blank"
          rel="noreferrer"
          className="text-sm text-risk-green hover:underline"
        >
          Open in DataHub →
        </a>
      </div>
      <div className="space-y-0">
        {lineage.lineage_chain.map((step, idx) => (
          <div key={step.step} className="flex gap-4">
            {/* Vertical line */}
            <div className="flex flex-col items-center">
              <div className="flex h-8 w-8 items-center justify-center rounded-full border border-risk-green/40 bg-[#141B2D] text-xs font-bold text-risk-green">
                {step.step}
              </div>
              {idx < lineage.lineage_chain.length - 1 && (
                <div className="w-px flex-1 bg-border" />
              )}
            </div>
            {/* Step content */}
            <div className="pb-6 flex-1">
              <div className="flex items-center gap-2">
                <span className="text-white font-medium">{step.entity}</span>
                <span className="rounded-full bg-[#1A2340] px-2 py-0.5 text-[10px] uppercase tracking-wide text-text-secondary">
                  {step.type}
                </span>
              </div>
              <div className="mt-1 text-xs text-text-secondary space-y-0.5">
                {step.last_updated && <div>Last updated: {step.last_updated}</div>}
                {step.freshness_hours !== undefined && <div>Freshness window: {step.freshness_hours}h</div>}
                {step.models_contributing && (
                  <div>Models: {step.models_contributing.join(', ')}</div>
                )}
                {step.execution_time && <div>Execution: {step.execution_time}</div>}
                {step.posterior_weights && <div>{step.posterior_weights}</div>}
                {step.formula && <div className="font-mono">{step.formula}</div>}
                {step.architecture && <div>{step.architecture}</div>}
                {step.channel && <div>Channel: {step.channel}</div>}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main Page ────────────────────────────────────────────

export default function DataHub() {
  const [models, setModels] = useState<ModelHealth[] | null>(null)
  const [freshness, setFreshness] = useState<Record<string, FreshnessStatus> | null>(null)
  const [lineage, setLineage] = useState<AlertLineage | null>(null)
  const [lineageAlertId, setLineageAlertId] = useState('')
  const [lineageLoading, setLineageLoading] = useState(false)
  const [syncResult, setSyncResult] = useState<DatahubSyncResult | null>(null)
  const [syncLoading, setSyncLoading] = useState(false)
  const [syncError, setSyncError] = useState<string | null>(null)

  // Agent chat state
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [chatResult, setChatResult] = useState<AgentQueryResult | null>(null)
  const [chatError, setChatError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetchModelHealth()
        if (!cancelled) setModels(res.models)
      } catch {
        if (!cancelled) setModels([])
      }
    })()
    ;(async () => {
      try {
        const res = await fetchPipelineFreshness()
        if (!cancelled) setFreshness(res.datasets)
      } catch {
        if (!cancelled) setFreshness({})
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const handleSync = async () => {
    setSyncLoading(true)
    setSyncError(null)
    try {
      const res = await triggerDatahubSync()
      setSyncResult(res)
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : 'Sync failed')
    } finally {
      setSyncLoading(false)
    }
  }

  const handleTraceLineage = async () => {
    if (!lineageAlertId.trim()) return
    setLineageLoading(true)
    try {
      const res = await fetchAlertLineage(lineageAlertId.trim())
      setLineage(res)
    } catch (err) {
      setLineage(null)
      setSyncError(err instanceof Error ? err.message : 'Lineage trace failed')
    } finally {
      setLineageLoading(false)
    }
  }

  const handleAgentQuery = async (query: string) => {
    if (!query.trim()) return
    setChatInput(query)
    setChatLoading(true)
    setChatError(null)
    try {
      const res = await queryHazardAgent(query.trim())
      setChatResult(res)
    } catch (err) {
      setChatError(err instanceof Error ? err.message : 'Agent request failed')
    } finally {
      setChatLoading(false)
    }
  }

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full" style={{ fontFamily: 'Inter, sans-serif' }}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white" style={{ fontFamily: 'Raleway, sans-serif', fontWeight: 700 }}>
            DataHub & Agent
          </h1>
          <p className="text-sm text-text-secondary mt-1">
            Metadata-driven intelligence — model health, pipeline freshness, lineage, and the HazardGraph agent
          </p>
        </div>
        <div className="flex items-center gap-3">
          <a
            href="http://localhost:9002"
            target="_blank"
            rel="noreferrer"
            className="rounded-lg border border-border bg-[#141B2D] px-4 py-2 text-sm text-text-secondary hover:text-white transition-colors"
          >
            Open DataHub UI
          </a>
          <button
            onClick={handleSync}
            disabled={syncLoading}
            className="rounded-lg bg-risk-green px-4 py-2 text-sm font-medium text-[#0A0F1E] hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {syncLoading ? 'Syncing…' : 'Sync to DataHub'}
          </button>
        </div>
      </div>

      {/* Sync result banner */}
      {syncResult && (
        <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-4">
          <p className="text-sm font-medium text-emerald-400">✓ DataHub sync complete</p>
          <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div><span className="text-text-secondary">Datasets:</span> <span className="text-white font-medium">{syncResult.datasets}</span></div>
            <div><span className="text-text-secondary">Models:</span> <span className="text-white font-medium">{syncResult.models}</span></div>
            <div><span className="text-text-secondary">Lineage edges:</span> <span className="text-white font-medium">{syncResult.lineage_edges}</span></div>
            <div><span className="text-text-secondary">Assertions:</span> <span className="text-white font-medium">{syncResult.assertions}</span></div>
          </div>
        </div>
      )}
      {syncError && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-400">
          {syncError}
        </div>
      )}

      <Tabs defaultValue="agent" className="w-full">
        <TabsList className="bg-[#141B2D] border border-border">
          <TabsTrigger value="agent">Agent Chat</TabsTrigger>
          <TabsTrigger value="models">Model Health</TabsTrigger>
          <TabsTrigger value="freshness">Pipeline Freshness</TabsTrigger>
          <TabsTrigger value="lineage">Lineage Trace</TabsTrigger>
        </TabsList>

        {/* ── Agent Chat ── */}
        <TabsContent value="agent" className="mt-4">
          <Card className="bg-[#141B2D] border-border">
            <CardHeader>
              <CardTitle className="text-white" style={{ fontFamily: 'Raleway, sans-serif' }}>
                HazardGraph Intelligence Agent
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-2">
                {SUGGESTED_QUERIES.map((q) => (
                  <button
                    key={q}
                    onClick={() => handleAgentQuery(q)}
                    disabled={chatLoading}
                    className="rounded-full border border-border bg-[#1A2340] px-3 py-1.5 text-xs text-text-secondary hover:text-white hover:border-risk-green/40 transition-colors disabled:opacity-50"
                  >
                    {q}
                  </button>
                ))}
              </div>

              <div className="flex gap-2">
                <input
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleAgentQuery(chatInput)}
                  placeholder="Ask about model health, data freshness, or alert lineage…"
                  className="flex-1 rounded-lg border border-border bg-[#0A0F1E] px-4 py-2.5 text-sm text-white placeholder:text-text-secondary focus:outline-none focus:border-risk-green/50"
                />
                <button
                  onClick={() => handleAgentQuery(chatInput)}
                  disabled={chatLoading || !chatInput.trim()}
                  className="rounded-lg bg-risk-green px-4 py-2.5 text-sm font-medium text-[#0A0F1E] hover:opacity-90 disabled:opacity-50 transition-opacity"
                >
                  {chatLoading ? 'Thinking…' : 'Ask'}
                </button>
              </div>

              {chatError && (
                <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-400">
                  {chatError}
                </div>
              )}

              {chatResult && (
                <div className="space-y-4">
                  <div className="rounded-lg border border-border bg-[#0A0F1E] p-4">
                    <p className="text-sm leading-relaxed text-white whitespace-pre-wrap">{chatResult.response}</p>
                  </div>

                  {/* Context used */}
                  <div className="rounded-lg border border-border bg-[#0A0F1E] p-4">
                    <p className="text-xs font-medium uppercase tracking-wide text-text-secondary mb-3">Context Used</p>
                    {chatResult.freshness && Object.keys(chatResult.freshness).length > 0 && (
                      <div className="mb-3">
                        <p className="text-xs text-text-secondary mb-1.5">Freshness</p>
                        <div className="flex flex-wrap gap-2">
                          {Object.entries(chatResult.freshness).map(([name, ds]) => (
                            <span key={name} className={cn('rounded-full px-2 py-0.5 text-xs', getFreshnessBadge(ds.status))}>
                              {name.split('_').slice(0, 2).join(' ')} · {ds.status}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    {chatResult.model_health?.models && (
                      <div>
                        <p className="text-xs text-text-secondary mb-1.5">Model Health</p>
                        <div className="flex flex-wrap gap-2">
                          {chatResult.model_health.models.map((m) => (
                            <span key={m.id} className={cn('rounded-full px-2 py-0.5 text-xs', getBrierBadge(m.brier_score))}>
                              {m.id} · {m.brier_score !== null ? m.brier_score.toFixed(3) : '—'}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Model Health ── */}
        <TabsContent value="models" className="mt-4">
          <Card className="bg-[#141B2D] border-border">
            <CardHeader>
              <CardTitle className="text-white" style={{ fontFamily: 'Raleway, sans-serif' }}>
                All 14 Models — Brier Scores & BMA Weights
              </CardTitle>
            </CardHeader>
            <CardContent>
              {models === null ? (
                <p className="text-sm text-text-secondary">Loading model health…</p>
              ) : models.length === 0 ? (
                <p className="text-sm text-text-secondary">No model data available.</p>
              ) : (
                <ModelHealthTable models={models} />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Pipeline Freshness ── */}
        <TabsContent value="freshness" className="mt-4">
          <Card className="bg-[#141B2D] border-border">
            <CardHeader>
              <CardTitle className="text-white" style={{ fontFamily: 'Raleway, sans-serif' }}>
                Upstream Dataset Freshness
              </CardTitle>
            </CardHeader>
            <CardContent>
              {freshness === null ? (
                <p className="text-sm text-text-secondary">Loading freshness…</p>
              ) : Object.keys(freshness).length === 0 ? (
                <p className="text-sm text-text-secondary">No freshness data available.</p>
              ) : (
                <FreshnessTable datasets={freshness} />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Lineage Trace ── */}
        <TabsContent value="lineage" className="mt-4">
          <Card className="bg-[#141B2D] border-border">
            <CardHeader>
              <CardTitle className="text-white" style={{ fontFamily: 'Raleway, sans-serif' }}>
                Alert Lineage Trace
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2">
                <input
                  value={lineageAlertId}
                  onChange={(e) => setLineageAlertId(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleTraceLineage()}
                  placeholder="Enter alert ID (e.g. alert_001)"
                  className="flex-1 rounded-lg border border-border bg-[#0A0F1E] px-4 py-2.5 text-sm text-white placeholder:text-text-secondary focus:outline-none focus:border-risk-green/50"
                />
                <button
                  onClick={handleTraceLineage}
                  disabled={lineageLoading || !lineageAlertId.trim()}
                  className="rounded-lg bg-risk-green px-4 py-2.5 text-sm font-medium text-[#0A0F1E] hover:opacity-90 disabled:opacity-50 transition-opacity"
                >
                  {lineageLoading ? 'Tracing…' : 'Trace'}
                </button>
              </div>

              {lineage && <LineageView lineage={lineage} />}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}