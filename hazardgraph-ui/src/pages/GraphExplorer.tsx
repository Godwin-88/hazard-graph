import { useState, useMemo, useCallback, useEffect } from 'react';
import { ForceGraph } from '../components/graph/ForceGraph';
import { NodeDetailSheet } from '../components/graph/NodeDetailSheet';
import { useGraphNodes, useGraphEdges } from '../hooks/useGraphData';
import type { GraphNode, GraphEdge } from '../hooks/useGraphData';
import { LoadingSpinner } from '../components/shared/LoadingSpinner';
import { RegimeBadge } from '../components/shared/RegimeBadge';

type Tab = 'full-graph' | 'causal-chains' | 'regime-map';

const REGIONS = [
  { id: 'region_kenya', name: 'Kenya' },
  { id: 'region_ethiopia', name: 'Ethiopia' },
  { id: 'region_somalia', name: 'Somalia' },
  { id: 'region_sudan', name: 'Sudan' },
  { id: 'region_south_sudan', name: 'South Sudan' },
  { id: 'region_uganda', name: 'Uganda' },
  { id: 'region_djibouti', name: 'Djibouti' },
  { id: 'region_eritrea', name: 'Eritrea' },
  { id: 'region_tanzania', name: 'Tanzania' },
  { id: 'region_burundi', name: 'Burundi' },
  { id: 'region_rwanda', name: 'Rwanda' },
];

const HAZARD_TYPES = [
  'drought', 'flood', 'locust', 'conflict', 'heatwave',
  'disease_outbreak', 'storm', 'landslide', 'frost', 'wildfire', 'market_shock',
];

// ── Causal Chains sub-tab ──────────────────────────────────

interface CausalChain {
  nodes: Array<{ id: string; label: string; type: string }>;
  weights: number[];
  cumulative_weight: number;
}

function CausalChainsView() {
  const [region, setRegion] = useState('region_kenya');
  const [hazardType, setHazardType] = useState('drought');
  const [chains, setChains] = useState<CausalChain[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchChains = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/graph/causal-chain/${region}/${hazardType}`, {
        headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error(`API error ${res.status}`);
      const data = await res.json();
      setChains(data.chains || []);
    } catch (err) {
      setError((err as Error).message || 'Failed to load causal chains');
      setChains(null);
    } finally {
      setLoading(false);
    }
  }, [region, hazardType]);

  return (
    <div className="flex h-full flex-col">
      {/* Controls */}
      <div className="flex flex-wrap items-end gap-3 border-b border-gray-800 px-4 py-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-400">Region</label>
          <select
            value={region}
            onChange={(e) => { setRegion(e.target.value); setChains(null); }}
            className="rounded border border-gray-700 bg-[#111827] px-3 py-1.5 text-sm text-white"
          >
            {REGIONS.map((r) => (
              <option key={r.id} value={r.id}>{r.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-gray-400">Hazard Type</label>
          <select
            value={hazardType}
            onChange={(e) => { setHazardType(e.target.value); setChains(null); }}
            className="rounded border border-gray-700 bg-[#111827] px-3 py-1.5 text-sm text-white"
          >
            {HAZARD_TYPES.map((h) => (
              <option key={h} value={h}>{h.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}</option>
            ))}
          </select>
        </div>

        <button
          onClick={fetchChains}
          disabled={loading}
          className="rounded-lg bg-[#0F4C81] px-4 py-1.5 text-sm font-medium text-white hover:bg-[#0F4C81]/80 transition-colors disabled:opacity-50"
        >
          {loading ? 'Tracing...' : 'Trace Causal Chain'}
        </button>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto p-4">
        {error && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-red-300 text-sm">
            {error}
          </div>
        )}

        {!loading && !error && !chains && (
          <div className="flex h-full items-center justify-center">
            <div className="text-center">
              <p className="text-gray-400">Causal Chain Explorer</p>
              <p className="mt-1 text-sm text-gray-500">
                Select a region and hazard type to trace the causal chain leading to a hazard
              </p>
            </div>
          </div>
        )}

        {!loading && !error && chains && chains.length === 0 && (
          <div className="text-center py-12 text-gray-500 text-sm">
            No causal chains found for this region and hazard type
          </div>
        )}

        {chains && chains.length > 0 && (
          <div className="space-y-4">
            {chains.map((chain, idx) => (
              <div key={idx} className="rounded-lg border border-gray-800 bg-[#111827] p-4">
                <div className="mb-3 flex items-center justify-between">
                  <span className="text-xs font-medium text-gray-400">
                    Chain {idx + 1} · {chain.nodes.length} nodes
                  </span>
                  <span className="rounded-full bg-purple-500/10 px-2 py-0.5 text-xs text-purple-400 border border-purple-500/30">
                    Cumulative weight: {chain.cumulative_weight.toFixed(3)}
                  </span>
                </div>

                {/* Chain visualization */}
                <div className="flex flex-wrap items-center gap-1.5">
                  {chain.nodes.map((node, i) => (
                    <div key={i} className="flex items-center gap-1.5">
                      <div className="rounded-md border border-gray-700 bg-[#0A0F1E] px-2.5 py-1.5">
                        <div className="text-xs font-medium text-white">{node.label || node.id}</div>
                        <div className="text-[10px] text-gray-500">{node.type}</div>
                      </div>
                      {i < chain.nodes.length - 1 && (
                        <div className="flex flex-col items-center">
                          <svg className="h-4 w-6 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                          </svg>
                          <span className="text-[9px] text-gray-600">
                            w={chain.weights[i]?.toFixed(2) ?? '?'}
                          </span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Regime Map sub-tab ─────────────────────────────────────

interface RegimeInfo {
  id: string;
  name: string;
  country: string;
  current_regime: string;
  posteriors: Record<string, number>;
}

function getAuthHeaders(): Record<string, string> {
  const token = sessionStorage.getItem('access_token');
  const headers: Record<string, string> = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

function RegimeMapView() {
  const [regimes, setRegimes] = useState<RegimeInfo[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/v1/graph/regimes', { headers: getAuthHeaders() })
      .then((res) => {
        if (!res.ok) throw new Error(`API error ${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (!cancelled) setRegimes(data.regions || []);
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message || 'Failed to load regimes');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const sortedRegimes = useMemo(() => {
    if (!regimes) return [];
    return [...regimes].sort((a, b) => {
      const order = ['FloodEmergency', 'SevereDrought', 'FloodWatch', 'DroughtOnset', 'Baseline'];
      return order.indexOf(a.current_regime) - order.indexOf(b.current_regime);
    });
  }, [regimes]);

  const stats = useMemo(() => {
    if (!regimes || regimes.length === 0) return { total: 0, drought: 0, flood: 0, normal: 0 };
    return {
      total: regimes.length,
      drought: regimes.filter((r) => r.current_regime.includes('Drought')).length,
      flood: regimes.filter((r) => r.current_regime.includes('Flood')).length,
      normal: regimes.filter((r) => r.current_regime === 'Baseline').length,
    };
  }, [regimes]);

  return (
    <div className="flex h-full flex-col">
      {/* Header with stats */}
      <div className="border-b border-gray-800 px-4 py-3">
        <div className="flex items-center gap-6">
          <div>
            <span className="text-xs text-gray-500">Total regions</span>
            <span className="ml-1 text-sm font-semibold text-white">{stats.total}</span>
          </div>
          <div>
            <span className="text-xs text-amber-400">Drought</span>
            <span className="ml-1 text-sm font-semibold text-white">{stats.drought}</span>
          </div>
          <div>
            <span className="text-xs text-blue-400">Flood</span>
            <span className="ml-1 text-sm font-semibold text-white">{stats.flood}</span>
          </div>
          <div>
            <span className="text-xs text-green-400">Baseline</span>
            <span className="ml-1 text-sm font-semibold text-white">{stats.normal}</span>
          </div>
        </div>
      </div>

      {/* Grid of region regime cards */}
      <div className="flex-1 overflow-y-auto p-4">
        {loading && (
          <div className="flex h-full items-center justify-center">
            <LoadingSpinner size="lg" label="Loading regime map..." />
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-red-300 text-sm">
            {error}
          </div>
        )}

        {!loading && !error && sortedRegimes.length === 0 && (
          <div className="flex h-full items-center justify-center text-gray-500 text-sm">
            No regime data available
          </div>
        )}

        {!loading && sortedRegimes.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {sortedRegimes.map((region) => {
              const topPosterior = Object.entries(region.posteriors)
                .sort(([, a], [, b]) => b - a)[0];
              const [topRegime, topProb] = topPosterior || ['Baseline', 0];
              return (
                <div key={region.id} className="rounded-lg border border-gray-800 bg-[#111827] p-4 hover:border-gray-600 transition-colors">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-sm font-semibold text-white capitalize">
                      {region.name || region.id.replace(/_/g, ' ')}
                    </h4>
                    <RegimeBadge regime={region.current_regime} />
                  </div>
                  <div className="text-xs text-gray-500 mb-2">{region.country || 'IGAD'}</div>
                  <div className="h-1.5 w-full rounded-full bg-gray-800 overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        topProb > 0.6 ? 'bg-green-500' : topProb > 0.3 ? 'bg-amber-500' : 'bg-red-500'
                      }`}
                      style={{ width: `${Math.min(100, topProb * 100)}%` }}
                    />
                  </div>
                  <div className="mt-1.5 text-[10px] text-gray-500">
                    Most likely: <span className="text-gray-400">{topRegime}</span> ({topProb.toFixed(2)})
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main GraphExplorer page ────────────────────────────────

export default function GraphExplorer() {
  const [activeTab, setActiveTab] = useState<Tab>('full-graph');
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  // Use the edges returned by /graph/nodes (nodesData.edges) rather than the
  // separate /graph/edges call. The nodes endpoint builds its edges from the
  // SAME records as its nodes, so edge source/target are guaranteed to match
  // the node ids. The standalone /graph/edges endpoint returns edges whose
  // source/target are Neo4j element_ids that do NOT match node domain ids,
  // which caused the "nodes but 0 edges" bug in the ForceGraph.
  const { data: nodesData, isLoading: nodesLoading, error: nodesError } = useGraphNodes();
  const { data: edgesData, isLoading: edgesLoading, error: edgesError } = useGraphEdges();

  const nodes: GraphNode[] = nodesData?.nodes ?? [];
  const edges: GraphEdge[] = (nodesData?.edges as GraphEdge[] | undefined) ?? [];

  const tabs: { id: Tab; label: string }[] = [
    { id: 'full-graph', label: 'Full Graph' },
    { id: 'causal-chains', label: 'Causal Chains' },
    { id: 'regime-map', label: 'Regime Map' },
  ];

  const isLoading = nodesLoading || edgesLoading;

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-gray-800 px-6 py-3">
        <div className="flex items-center justify-between">
          <h1 className="font-['Raleway'] text-xl font-bold text-white">
            Graph Explorer
          </h1>
          {nodes.length > 0 && (
            <span className="text-sm text-gray-500">
              {nodes.length} nodes · {edges.length} edges
            </span>
          )}
        </div>

        {/* Tabs */}
        <div className="mt-3 flex gap-1 rounded-lg bg-gray-800/50 p-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-1 rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'bg-[#0F4C81] text-white'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content area */}
      <div className="relative flex-1">
        {activeTab === 'full-graph' && (
          <>
            {isLoading && (
              <div className="flex h-full items-center justify-center">
                <LoadingSpinner size="lg" label="Loading graph data..." />
              </div>
            )}

            {!isLoading && (nodesError || edgesError) && (
              <div className="flex h-full items-center justify-center">
                <div className="text-center">
                  <p className="text-red-400">Failed to load graph data</p>
                  <p className="mt-1 text-sm text-gray-500">
                    {nodesError instanceof Error ? nodesError.message : edgesError instanceof Error ? edgesError.message : 'Unknown error'}
                  </p>
                </div>
              </div>
            )}

            {!isLoading && !nodesError && nodes.length > 0 && (
              <ForceGraph
                nodes={nodes as GraphNode[]}
                edges={edges}
                onNodeClick={(node) => setSelectedNode(node)}
              />
            )}

            {!isLoading && !nodesError && nodes.length === 0 && (
              <div className="flex h-full items-center justify-center text-gray-500 text-sm">
                No graph data available
              </div>
            )}
          </>
        )}

        {activeTab === 'causal-chains' && <CausalChainsView />}
        {activeTab === 'regime-map' && <RegimeMapView />}

        {/* Node detail modal */}
        <NodeDetailSheet
          node={selectedNode}
          edges={edges}
          nodesMap={Object.fromEntries(nodes.map((n) => [String(n.id), n]))}
          onClose={() => setSelectedNode(null)}
          onJumpTo={(nodeId) => {
            const next = nodes.find((n) => String(n.id) === String(nodeId));
            if (next) setSelectedNode(next);
          }}
        />
      </div>
    </div>
  );
}