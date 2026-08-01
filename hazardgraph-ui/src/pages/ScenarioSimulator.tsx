import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { RegimeBadge } from '@/components/shared/RegimeBadge'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import ModelRunner from '@/components/scenarios/ModelRunner'
import {
  fetchPolicyRecommendations,
  triggerPolicyTraining,
  runCascadeSimulation,
  fetchHazardClusters,
  refreshClusters,
} from '@/lib/api'
import type { PolicyRecommendation, CascadeResult, HazardCluster } from '@/types'

const REGIONS = [
  'kenya', 'ethiopia', 'somalia', 'sudan', 'south_sudan',
  'uganda', 'djibouti', 'eritrea', 'tanzania', 'burundi', 'rwanda',
]

const ACTION_COLORS: Record<string, string> = {
  NO_ALERT: 'bg-gray-500/20 text-gray-300 border-gray-500/30',
  LOW_ADVISORY: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  MEDIUM_SMS: 'bg-amber-500/20 text-amber-300 border-amber-500/30 animate-pulse',
  HIGH_ESCALATE: 'bg-red-500/20 text-red-300 border-red-500/30 animate-pulse',
}

function PolicyRecommendationCard({ rec }: { rec: PolicyRecommendation }) {
  return (
    <Card className="border-border/50 bg-[#12172B]">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-semibold text-white capitalize">{rec.region_id.replace('_', ' ')}</h4>
          <span className={`px-2 py-0.5 rounded text-xs font-medium border ${ACTION_COLORS[rec.action_label] || ''}`}>
            {rec.action_label.replace('_', ' ')}
          </span>
        </div>
        <div className="mb-2">
          <div className="flex justify-between text-xs text-text-muted mb-1">
            <span>Confidence</span>
            <span>{(rec.probability * 100).toFixed(0)}%</span>
          </div>
          <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-risk-green rounded-full transition-all"
              style={{ width: `${rec.probability * 100}%` }}
            />
          </div>
        </div>
        <p className="text-xs text-text-secondary">{rec.reasoning}</p>
      </CardContent>
    </Card>
  )
}

function CascadeSimulatorView() {
  const [sourceRegion, setSourceRegion] = useState('somalia')
  const [horizonWeeks, setHorizonWeeks] = useState(8)
  const [nPaths, setNPaths] = useState(500)
  const [result, setResult] = useState<CascadeResult | null>(null)

  const cascadeMutation = useMutation({
    mutationFn: () => runCascadeSimulation(sourceRegion, horizonWeeks, nPaths),
    onSuccess: (data) => setResult(data),
  })

  return (
    <div className="space-y-6">
      <Card className="border-border/50 bg-[#12172B]">
        <CardHeader>
          <CardTitle className="text-white text-lg">Contagion Cascade Simulator</CardTitle>
          <CardDescription className="text-text-muted">
            Model how a food crisis spreads through the IGAD region network
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm text-text-secondary mb-1 block">Source Region</label>
            <select
              value={sourceRegion}
              onChange={(e) => setSourceRegion(e.target.value)}
              className="w-full bg-[#0A0F1E] border border-border/50 rounded px-3 py-2 text-white text-sm"
            >
              {REGIONS.map((r) => (
                <option key={r} value={r}>{r.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-sm text-text-secondary mb-1 block">
              Horizon: {horizonWeeks} weeks
            </label>
            <input
              type="range"
              min={4}
              max={12}
              value={horizonWeeks}
              onChange={(e) => setHorizonWeeks(Number(e.target.value))}
              className="w-full"
            />
          </div>

          <div>
            <label className="text-sm text-text-secondary mb-1 block">
              Simulation Paths: {nPaths}
            </label>
            <input
              type="range"
              min={100}
              max={1000}
              step={100}
              value={nPaths}
              onChange={(e) => setNPaths(Number(e.target.value))}
              className="w-full"
            />
          </div>

          <button
            onClick={() => cascadeMutation.mutate()}
            disabled={cascadeMutation.isPending}
            className="px-4 py-2 bg-risk-green/20 text-risk-green border border-risk-green/30 rounded hover:bg-risk-green/30 transition-colors text-sm"
          >
            {cascadeMutation.isPending ? 'Running Simulation...' : 'Run Simulation'}
          </button>
        </CardContent>
      </Card>

      {cascadeMutation.isError && (
        <Card className="border-red-500/30 bg-red-500/10">
          <CardContent className="p-4 text-red-300 text-sm">
            Simulation failed: {(cascadeMutation.error as Error).message}
          </CardContent>
        </Card>
      )}

      {result && (
        <>
          <Card className="border-risk-green/30 bg-risk-green/5">
            <CardContent className="p-4">
              <div className="text-2xl font-bold text-risk-green mb-1">
                {result.expected_affected_population_millions.toFixed(1)}M
              </div>
              <div className="text-sm text-text-secondary">
                People at risk from {result.source_region.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())} cascade
              </div>
              <div className="mt-2 text-xs text-risk-green">
                Chain Breaker: <strong className="capitalize">{result.critical_intervention_node.replace('_', ' ')}</strong>
                {' '}— most effective intervention target
              </div>
            </CardContent>
          </Card>

          <Card className="border-border/50 bg-[#12172B]">
            <CardHeader>
              <CardTitle className="text-white text-sm">Cascade Probabilities</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {Object.entries(result.cascade_probabilities)
                  .sort(([, a], [, b]) => b - a)
                  .map(([region, prob]) => (
                    <div key={region} className="flex items-center gap-3">
                      <span className="text-xs text-text-secondary w-24 capitalize truncate">
                        {region.replace('_', ' ')}
                      </span>
                      <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${
                            prob > 0.5 ? 'bg-red-500' : prob > 0.2 ? 'bg-amber-500' : 'bg-risk-green'
                          }`}
                          style={{ width: `${prob * 100}%` }}
                        />
                      </div>
                      <span className="text-xs text-text-muted w-12 text-right">
                        {(prob * 100).toFixed(0)}%
                      </span>
                    </div>
                  ))}
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}

function ClustersView() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['hazard-clusters'],
    queryFn: fetchHazardClusters,
  })

  const refreshMutation = useMutation({
    mutationFn: refreshClusters,
    onSuccess: () => refetch(),
  })

  if (isLoading) return <LoadingSpinner />
  if (error) return <div className="text-red-400 text-sm">Failed to load clusters</div>

  const clusters = data?.clusters || []

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-white text-lg font-semibold">Aid Allocation Clusters ({clusters.length})</h3>
        <button
          onClick={() => refreshMutation.mutate()}
          disabled={refreshMutation.isPending}
          className="px-3 py-1.5 text-xs bg-blue-500/20 text-blue-300 border border-blue-500/30 rounded hover:bg-blue-500/30 transition-colors"
        >
          {refreshMutation.isPending ? 'Refreshing...' : 'Refresh Clusters'}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {clusters.map((cluster) => (
          <Card key={cluster.id} className="border-border/50 bg-[#12172B]">
            <CardHeader className="pb-2">
              <CardTitle className="text-white text-sm">{cluster.label}</CardTitle>
              <CardDescription className="text-text-muted text-xs">
                {cluster.member_count} regions · Risk: {cluster.risk_score?.toFixed(0) || 'N/A'}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-1.5 mb-2">
                {(cluster.member_regions || []).map((r: string) => (
                  <span key={r} className="px-2 py-0.5 bg-[#0A0F1E] rounded text-xs text-text-secondary capitalize">
                    {r.replace('_', ' ')}
                  </span>
                ))}
              </div>
              <div className="flex items-center gap-2">
                <RegimeBadge regime={cluster.dominant_hazard} />
                <span className="text-xs text-text-muted">dominant hazard</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}

export default function ScenarioSimulator() {
  const policyQuery = useQuery({
    queryKey: ['policy-recommendations'],
    queryFn: fetchPolicyRecommendations,
    refetchInterval: 300_000,
  })

  const trainingMutation = useMutation({
    mutationFn: triggerPolicyTraining,
  })

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Scenario Simulator</h1>
        <p className="text-sm text-text-muted mt-1">
          DRL policy recommendations, contagion cascades, and aid allocation clusters
        </p>
      </div>

      <Tabs defaultValue="models" className="w-full">
        <TabsList className="bg-[#12172B] border border-border/50">
          <TabsTrigger value="models" className="text-text-secondary data-[state=active]:text-white data-[state=active]:bg-risk-green/20">
            Model Runner
          </TabsTrigger>
          <TabsTrigger value="policy" className="text-text-secondary data-[state=active]:text-white data-[state=active]:bg-risk-green/20">
            DRL Policy
          </TabsTrigger>
          <TabsTrigger value="cascade" className="text-text-secondary data-[state=active]:text-white data-[state=active]:bg-risk-green/20">
            Contagion Cascade
          </TabsTrigger>
          <TabsTrigger value="clusters" className="text-text-secondary data-[state=active]:text-white data-[state=active]:bg-risk-green/20">
            Aid Clusters
          </TabsTrigger>
        </TabsList>

        <TabsContent value="models" className="mt-4">
          <ModelRunner />
        </TabsContent>

        <TabsContent value="policy" className="mt-4 space-y-4">
          <div className="flex justify-between items-center">
            <div>
              <h3 className="text-white text-lg font-semibold">DRL Policy Recommendations</h3>
              <p className="text-xs text-text-muted">
                GNN-PPO policy: {policyQuery.data?.model || 'loading...'}
              </p>
            </div>
            <button
              onClick={() => trainingMutation.mutate()}
              disabled={trainingMutation.isPending}
              className="px-3 py-1.5 text-xs bg-purple-500/20 text-purple-300 border border-purple-500/30 rounded hover:bg-purple-500/30 transition-colors"
            >
              {trainingMutation.isPending ? 'Training...' : 'Retrain Policy'}
            </button>
          </div>

          {trainingMutation.isSuccess && (
            <div className="p-3 bg-purple-500/10 border border-purple-500/30 rounded text-purple-300 text-xs">
              Training started — will complete in ~5 minutes
            </div>
          )}

          {policyQuery.isLoading && <LoadingSpinner />}
          {policyQuery.error && (
            <div className="p-4 bg-red-500/10 border border-red-500/30 rounded text-red-300 text-sm">
              Failed to load policy recommendations. The DRL model may need training first.
            </div>
          )}

          {policyQuery.data && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {policyQuery.data.recommendations.map((rec) => (
                <PolicyRecommendationCard key={rec.region_id} rec={rec} />
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="cascade" className="mt-4">
          <CascadeSimulatorView />
        </TabsContent>

        <TabsContent value="clusters" className="mt-4">
          <ClustersView />
        </TabsContent>
      </Tabs>
    </div>
  )
}