import { useState } from 'react';
import { ForceGraph } from '../components/graph/ForceGraph';
import { NodeDetailSheet } from '../components/graph/NodeDetailSheet';
import { useGraphNodes, useGraphEdges } from '../hooks/useGraphData';
import type { GraphNode } from '../hooks/useGraphData';
import { LoadingSpinner } from '../components/shared/LoadingSpinner';

type Tab = 'full-graph' | 'causal-chains' | 'regime-map';

export default function GraphExplorer() {
  const [activeTab, setActiveTab] = useState<Tab>('full-graph');
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  const { data: nodes, isLoading: nodesLoading, error: nodesError } = useGraphNodes();
  const { data: edges, isLoading: edgesLoading, error: edgesError } = useGraphEdges();

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
          {nodes && edges && (
            <span className="text-sm text-gray-500">
              {Array.isArray(nodes) ? nodes.length : 0} nodes · {Array.isArray(edges) ? edges.length : 0} edges
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

        {!isLoading && !nodesError && activeTab === 'full-graph' && nodes && edges && (
          <ForceGraph
            nodes={Array.isArray(nodes) ? nodes as GraphNode[] : []}
            edges={Array.isArray(edges) ? edges : []}
            onNodeClick={(node) => setSelectedNode(node)}
          />
        )}

        {!isLoading && activeTab === 'causal-chains' && (
          <div className="flex h-full items-center justify-center">
            <div className="text-center">
              <p className="text-gray-400">Causal Chains</p>
              <p className="mt-1 text-sm text-gray-500">
                Select a region and hazard type to trace causal chains
              </p>
            </div>
          </div>
        )}

        {!isLoading && activeTab === 'regime-map' && (
          <div className="flex h-full items-center justify-center">
            <div className="text-center">
              <p className="text-gray-400">Regime Map</p>
              <p className="mt-1 text-sm text-gray-500">
                Simplified regime visualisation coming soon
              </p>
            </div>
          </div>
        )}

        {/* Node detail sheet */}
        <NodeDetailSheet
          node={selectedNode}
          onClose={() => setSelectedNode(null)}
        />
      </div>
    </div>
  );
}