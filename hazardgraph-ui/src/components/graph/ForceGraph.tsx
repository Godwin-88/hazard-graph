import { useRef, useState, useEffect, useCallback, useMemo } from 'react';

interface GraphNode {
  id: string;
  label: string;
  type: string;
  properties?: Record<string, unknown>;
  [key: string]: unknown;
}

interface GraphEdge {
  source: string;
  target: string;
  type: string;
  weight?: number;
  [key: string]: unknown;
}

interface DisplayNode {
  id: string;
  label: string;
  type: string;
  isAggregate: boolean;
  count: number;
}

interface DisplayEdge {
  source: string;
  target: string;
  type: string;
  weight: number;
}

interface ForceGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick?: (node: GraphNode) => void;
}

const NODE_COLORS: Record<string, string> = {
  Region: '#0F4C81',
  RainfallSignal: '#3B82F6',
  IPCPhaseSignal: '#EF4444',
  FoodPriceSignal: '#F59E0B',
  CausalEdge: '#8B5CF6',
  HazardRegime: '#10B981',
  HazardType: '#EC4899',
  InterventionStrategy: '#06B6D4',
  ForecastSignal: '#84CC16',
  VulnerabilityIndex: '#F97316',
  StochasticSignal: '#A855F7',
  MLForecast: '#D946EF',
  BMAScore: '#22C55E',
  Alert: '#F43F5E',
  DataSource: '#64748B',
  HazardCluster: '#14B8A6',
  NDVISignal: '#22C55E',
  ConflictSignal: '#DC2626',
};

const NODE_SIZES: Record<string, number> = {
  Region: 16,
  HazardRegime: 12,
  HazardType: 10,
  InterventionStrategy: 9,
  CausalEdge: 8,
  RainfallSignal: 7,
  FoodPriceSignal: 7,
  IPCPhaseSignal: 8,
  ForecastSignal: 7,
  VulnerabilityIndex: 7,
  StochasticSignal: 7,
  MLForecast: 7,
  BMAScore: 8,
  Alert: 10,
  DataSource: 6,
  HazardCluster: 11,
  NDVISignal: 7,
  ConflictSignal: 8,
};

// Build a distinguishing label for an individual node so members of the same
// type (e.g. hundreds of IPCPhaseSignal nodes) are not all labelled identically.
function nodeDisplayLabel(n: GraphNode): string {
  const p = (n.properties || {}) as Record<string, unknown>;
  if (n.type === 'Region') return String(p.name || n.label || n.id);
  if (p.region_id && p.date) {
    return `${String(p.region_id).replace('region_', '')} · ${String(p.date)}`;
  }
  if (p.region_id) return String(p.region_id).replace('region_', '');
  if (p.name) return String(p.name);
  if (p.title) return String(p.title);
  if (p.commodity) return `${String(p.commodity)} · ${String(p.region_id || '').replace('region_', '')}`;
  return String(n.label || n.id);
}

export function ForceGraph({ nodes, edges, onNodeClick }: ForceGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<any>(null);
  // Default to the type-overview so the graph is readable instead of dumping
  // thousands of indistinguishable nodes at once.
  const [viewMode, setViewMode] = useState<'types' | 'nodes'>('types');
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set());
  const [activeTypes, setActiveTypes] = useState<Set<string>>(new Set());
  const [minWeight, setMinWeight] = useState(0);
  const [graphLibLoaded, setGraphLibLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [typesInitialized, setTypesInitialized] = useState(false);

  // Dynamically load the force graph library
  useEffect(() => {
    let cancelled = false;
    import('react-force-graph-2d').then(() => {
      if (!cancelled) setGraphLibLoaded(true);
    }).catch((err) => {
      if (!cancelled) {
        setError('Failed to load graph library: ' + (err as Error).message);
        setGraphLibLoaded(false);
      }
    });
    return () => { cancelled = true; };
  }, []);

  const nodeTypes = useMemo(() => {
    const dataTypes = new Set<string>();
    nodes.forEach((n) => dataTypes.add(n.type));
    return Array.from(dataTypes);
  }, [nodes]);

  // Enable ALL types by default so edges are not dropped by the visibility filter.
  useEffect(() => {
    if (typesInitialized || nodeTypes.length === 0) return;
    setActiveTypes(new Set(nodeTypes));
    setTypesInitialized(true);
  }, [nodeTypes, typesInitialized]);

  // ── Type aggregates ──────────────────────────────────────
  // Group nodes by type; each type becomes one aggregate node (unless expanded).
  const nodesByType = useMemo(() => {
    const map = new Map<string, GraphNode[]>();
    nodes.forEach((n) => {
      if (!map.has(n.type)) map.set(n.type, []);
      map.get(n.type)!.push(n);
    });
    return map;
  }, [nodes]);

  // ── Display nodes ────────────────────────────────────────
  const displayNodes = useMemo<DisplayNode[]>(() => {
    if (viewMode === 'nodes') {
      // All-nodes mode: show every node (of an enabled type) with a
      // distinguishing label.
      return nodes
        .filter((n) => activeTypes.has(n.type))
        .map((n) => ({
          id: String(n.id),
          label: nodeDisplayLabel(n),
          type: n.type,
          isAggregate: false,
          count: 1,
        }));
    }
    // Type-overview mode: one aggregate node per enabled type, unless that
    // type is expanded (then show its member nodes with distinguishing labels).
    const result: DisplayNode[] = [];
    nodesByType.forEach((members, type) => {
      if (!activeTypes.has(type)) return;
      if (expandedTypes.has(type)) {
        members.slice(0, 300).forEach((m) => {
          result.push({
            id: String(m.id),
            label: nodeDisplayLabel(m),
            type,
            isAggregate: false,
            count: 1,
          });
        });
      } else {
        result.push({
          id: `type:${type}`,
          label: `${type} (${members.length})`,
          type,
          isAggregate: true,
          count: members.length,
        });
      }
    });
    return result;
  }, [viewMode, nodes, nodesByType, expandedTypes, activeTypes]);

  // ── Display edges ────────────────────────────────────────
  const displayEdges = useMemo<DisplayEdge[]>(() => {
    const result: DisplayEdge[] = [];
    const visibleIds = new Set(displayNodes.map((n) => n.id));

    edges.forEach((e) => {
      const src = nodes.find((n) => String(n.id) === String(e.source));
      const tgt = nodes.find((n) => String(n.id) === String(e.target));
      if (!src || !tgt) return;

      if (viewMode === 'nodes') {
        if (visibleIds.has(String(e.source)) && visibleIds.has(String(e.target))) {
          result.push({
            source: String(e.source),
            target: String(e.target),
            type: e.type,
            weight: e.weight ?? 1,
          });
        }
        return;
      }

      // Type-overview: map each endpoint to either its member id (if that type
      // is expanded) or its aggregate type id (if collapsed).
      const srcVisible = expandedTypes.has(src.type)
        ? visibleIds.has(String(e.source))
        : visibleIds.has(`type:${src.type}`);
      const tgtVisible = expandedTypes.has(tgt.type)
        ? visibleIds.has(String(e.target))
        : visibleIds.has(`type:${tgt.type}`);
      if (srcVisible && tgtVisible) {
        result.push({
          source: expandedTypes.has(src.type) ? String(e.source) : `type:${src.type}`,
          target: expandedTypes.has(tgt.type) ? String(e.target) : `type:${tgt.type}`,
          type: e.type,
          weight: e.weight ?? 1,
        });
      }
    });
    return result;
  }, [viewMode, edges, nodes, displayNodes, expandedTypes]);

  // Aggregate edge counts for the relationship legend (type-overview).
  const aggregateEdgeCounts = useMemo(() => {
    const counts = new Map<string, number>();
    displayEdges.forEach((e) => {
      counts.set(e.type, (counts.get(e.type) || 0) + 1);
    });
    return counts;
  }, [displayEdges]);

  const graphData = useMemo(() => ({
    nodes: displayNodes.map((n) => ({
      id: n.id,
      label: n.label,
      type: n.type,
      isAggregate: n.isAggregate,
      count: n.count,
      val: n.isAggregate
        ? Math.min(18 + n.count / 40, 38)
        : (NODE_SIZES[n.type] || 7),
    })),
    links: displayEdges.map((e) => ({
      source: e.source,
      target: e.target,
      type: e.type,
      weight: e.weight,
      value: (e.weight ?? 1) * 2,
    })),
  }), [displayNodes, displayEdges]);

  const handleNodeClick = useCallback(
    (node: { id: string }) => {
      // In type-overview mode, clicking an aggregate node expands/collapses it.
      if (viewMode === 'types') {
        const agg = displayNodes.find((n) => n.id === node.id && n.isAggregate);
        if (agg) {
          setExpandedTypes((prev) => {
            const next = new Set(prev);
            if (next.has(agg.type)) next.delete(agg.type);
            else next.add(agg.type);
            return next;
          });
          return;
        }
      }
      // Otherwise open the detail sheet for the underlying node.
      const found = nodes.find((n) => String(n.id) === String(node.id));
      if (found && onNodeClick) onNodeClick(found);
    },
    [viewMode, displayNodes, nodes, onNodeClick]
  );

  const edgeTypes = useMemo(() => {
    const types = new Set<string>();
    edges.forEach((e) => types.add(e.type));
    return Array.from(types);
  }, [edges]);

  const allTypesEnabled = activeTypes.size === nodeTypes.length && nodeTypes.length > 0;

  const toggleAllTypes = () => {
    if (allTypesEnabled) setActiveTypes(new Set());
    else setActiveTypes(new Set(nodeTypes));
  };

  if (error) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <p className="text-red-400">Graph library error</p>
          <p className="mt-1 text-sm text-gray-500">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full">
      {/* Graph area */}
      <div ref={containerRef} className="h-full w-full">
        <GraphVisualization
          containerRef={containerRef}
          graphData={graphData}
          graphLibLoaded={graphLibLoaded}
          onNodeClick={handleNodeClick}
        />
      </div>

      {/* Controls overlay */}
      <div className="absolute top-4 right-4 w-60 space-y-3 rounded-lg border border-gray-800 bg-[#111827]/95 p-3 shadow-xl backdrop-blur-sm z-10">
        {/* View mode toggle */}
        <div className="flex rounded-lg border border-gray-700 bg-gray-800 p-0.5">
          <button
            onClick={() => setViewMode('types')}
            className={`flex-1 rounded-md px-2 py-1 text-xs font-medium transition-colors ${
              viewMode === 'types' ? 'bg-[#0F4C81] text-white' : 'text-gray-400 hover:text-white'
            }`}
          >
            By Type
          </button>
          <button
            onClick={() => setViewMode('nodes')}
            className={`flex-1 rounded-md px-2 py-1 text-xs font-medium transition-colors ${
              viewMode === 'nodes' ? 'bg-[#0F4C81] text-white' : 'text-gray-400 hover:text-white'
            }`}
          >
            All Nodes
          </button>
        </div>

        {viewMode === 'types' && (
          <p className="text-[10px] text-gray-500">
            Click a type node to expand its members. Click again to collapse.
          </p>
        )}

        {/* Type filter */}
        <div>
          <div className="mb-1 flex items-center justify-between">
            <span className="text-xs font-medium text-gray-400">Node types</span>
            <button
              onClick={toggleAllTypes}
              className="text-xs text-[#00C896] hover:text-[#00C896]/80"
            >
              {allTypesEnabled ? 'None' : 'All'}
            </button>
          </div>
          <div className="max-h-40 space-y-1 overflow-y-auto pr-1">
            {nodeTypes.length === 0 && (
              <p className="text-xs text-gray-500">No node types available</p>
            )}
            {nodeTypes.map((type) => (
              <label key={type} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={activeTypes.has(type)}
                  onChange={() => {
                    const next = new Set(activeTypes);
                    if (next.has(type)) next.delete(type);
                    else next.add(type);
                    setActiveTypes(next);
                  }}
                  className="rounded border-gray-600 bg-gray-800 text-[#0F4C81] focus:ring-[#0F4C81]"
                />
                <span
                  className="text-xs"
                  style={{ color: NODE_COLORS[type] || '#9CA3AF' }}
                >
                  {type}
                </span>
              </label>
            ))}
          </div>
        </div>

        {/* Edge weight threshold */}
        <div>
          <div className="mb-1 text-xs font-medium text-gray-400">
            Min weight: {minWeight.toFixed(1)}
          </div>
          <input
            type="range"
            min={0}
            max={1}
            step={0.1}
            value={minWeight}
            onChange={(e) => setMinWeight(parseFloat(e.target.value))}
            className="w-full accent-[#00C896]"
          />
        </div>

        {/* Relationship types legend */}
        <div>
          <p className="text-xs font-medium text-gray-400 mb-1">Relationships</p>
          {edgeTypes.length === 0 ? (
            <p className="text-[10px] text-gray-500">No relationships found</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {edgeTypes.slice(0, 10).map((type) => (
                <span
                  key={type}
                  className="px-1.5 py-0.5 rounded text-[10px] font-medium text-purple-300 bg-purple-500/10 border border-purple-500/30"
                >
                  {type}
                  {viewMode === 'types' && aggregateEdgeCounts.has(type)
                    ? ` (${aggregateEdgeCounts.get(type)})`
                    : ''}
                </span>
              ))}
              {edgeTypes.length > 10 && (
                <span className="px-1.5 py-0.5 rounded text-[10px] text-gray-400 bg-gray-800">
                  +{edgeTypes.length - 10} more
                </span>
              )}
            </div>
          )}
        </div>

        {/* Stats */}
        <div className="border-t border-gray-800 pt-2 text-xs text-gray-500">
          {displayNodes.length} nodes · {displayEdges.length} edges
          {!graphLibLoaded && ' · using fallback layout'}
        </div>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────
// Graph visualization that properly uses react-force-graph-2d
// ────────────────────────────────────────────────────────────

function GraphVisualization({
  containerRef,
  graphData,
  graphLibLoaded,
  onNodeClick,
}: {
  containerRef: React.RefObject<HTMLDivElement>;
  graphData: {
    nodes: { id: string; label: string; type: string; isAggregate: boolean; count: number; val: number }[];
    links: { source: string; target: string; type: string; weight: number; value: number }[];
  };
  graphLibLoaded: boolean;
  onNodeClick: (node: { id: string }) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [GraphComponent, setGraphComponent] = useState<React.ComponentType<any> | null>(null);
  const graphInstanceRef = useRef<any>(null);
  const frameRef = useRef<number>(0);

  // Load the actual component when library is ready
  useEffect(() => {
    if (!graphLibLoaded) return;
    let cancelled = false;
    import('react-force-graph-2d').then((mod) => {
      if (!cancelled) setGraphComponent(() => mod.default);
    });
    return () => { cancelled = true; };
  }, [graphLibLoaded]);

  // Setup canvas when component fails to load or while waiting
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || GraphComponent) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    if (containerRef.current) {
      canvas.width = containerRef.current.clientWidth || 800;
      canvas.height = containerRef.current.clientHeight || 600;
    }

    const w = canvas.width;
    const h = canvas.height;

    // Cancel previous animation
    cancelAnimationFrame(frameRef.current);

    // Simple circular layout fallback with edges
    const positions = graphData.nodes.map((n, i) => {
      const angle = (2 * Math.PI * i) / Math.max(graphData.nodes.length, 1);
      const radius = Math.min(w, h) * 0.35;
      return {
        ...n,
        x: w / 2 + radius * Math.cos(angle),
        y: h / 2 + radius * Math.sin(angle),
      };
    });

    const draw = () => {
      ctx.fillStyle = '#0A0F1E';
      ctx.fillRect(0, 0, w, h);

      // Draw edges first
      graphData.links.forEach((link) => {
        const src = positions.find((n) => n.id === link.source);
        const tgt = positions.find((n) => n.id === link.target);
        if (src && tgt) {
          ctx.beginPath();
          ctx.moveTo(src.x, src.y);
          ctx.lineTo(tgt.x, tgt.y);
          ctx.strokeStyle = link.weight > 0.6 ? '#7C3AED' : link.weight > 0.3 ? '#4C1D95' : '#312E81';
          ctx.globalAlpha = 0.3 + link.weight * 0.7;
          ctx.lineWidth = 0.5 + link.weight * 2;
          ctx.stroke();
          ctx.globalAlpha = 1;
        }
      });

      // Draw nodes
      positions.forEach((node) => {
        const color = NODE_COLORS[node.type] || '#6B7280';
        const size = node.val;

        // Glow effect
        ctx.beginPath();
        ctx.arc(node.x, node.y, size + 3, 0, 2 * Math.PI);
        ctx.fillStyle = `${color}22`;
        ctx.fill();

        // Node body
        ctx.beginPath();
        ctx.arc(node.x, node.y, size, 0, 2 * Math.PI);
        ctx.fillStyle = color;
        ctx.fill();

        // Aggregate ring
        if (node.isAggregate) {
          ctx.beginPath();
          ctx.arc(node.x, node.y, size + 4, 0, 2 * Math.PI);
          ctx.strokeStyle = 'rgba(255,255,255,0.5)';
          ctx.lineWidth = 2;
          ctx.stroke();
        }

        // Node border
        ctx.strokeStyle = 'rgba(255,255,255,0.2)';
        ctx.lineWidth = 1;
        ctx.stroke();

        // Label
        ctx.fillStyle = '#E5E7EB';
        ctx.font = node.isAggregate ? 'bold 11px Inter, sans-serif' : '10px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(node.label, node.x, node.y + size + 14);
      });

      frameRef.current = requestAnimationFrame(draw);
    };

    draw();

    // Click handler
    const handleClick = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const clicked = positions.find((n) => {
        const dx = mx - n.x;
        const dy = my - n.y;
        return Math.sqrt(dx * dx + dy * dy) < 20;
      });
      if (clicked) onNodeClick({ id: clicked.id });
    };
    canvas.addEventListener('click', handleClick);

    const handleResize = () => {
      if (containerRef.current) {
        canvas.width = containerRef.current.clientWidth || 800;
        canvas.height = containerRef.current.clientHeight || 600;
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      cancelAnimationFrame(frameRef.current);
      canvas.removeEventListener('click', handleClick);
      window.removeEventListener('resize', handleResize);
    };
  }, [graphData, GraphComponent, containerRef, onNodeClick]);

  // If the force graph library is loaded, render the actual component
  if (GraphComponent) {
    return (
      <GraphComponent
        ref={(el: any) => { graphInstanceRef.current = el; }}
        graphData={graphData}
        nodeLabel="label"
        nodeColor={(node: any) => NODE_COLORS[node.type] || '#6B7280'}
        nodeVal={nodeVal}
        nodeCanvasObject={nodeCanvasObject}
        linkColor={(link: any) => {
          const w = link.weight ?? 1;
          return w > 0.6 ? 'rgba(139, 92, 246, 0.7)' : w > 0.3 ? 'rgba(139, 92, 246, 0.4)' : 'rgba(75, 85, 99, 0.3)';
        }}
        linkWidth={(link: any) => (link.weight ?? 1) * 2 + 0.5}
        onNodeClick={onNodeClick}
        backgroundColor="#0A0F1E"
        width={containerRef.current?.clientWidth || 800}
        height={containerRef.current?.clientHeight || 600}
      />
    );
  }

  // Fallback canvas while library is loading
  return (
    <canvas
      ref={canvasRef}
      width={containerRef.current?.clientWidth || 800}
      height={containerRef.current?.clientHeight || 600}
      className="h-full w-full"
      style={{ display: 'block' }}
    />
  );
}

// Helper functions for force graph rendering
function nodeVal(node: any): number {
  if (node.isAggregate) return Math.min(18 + node.count / 40, 38);
  return NODE_SIZES[node.type] || 7;
}

function nodeCanvasObject(node: any, ctx: CanvasRenderingContext2D, globalScale: number) {
  const label = node.label || node.id;
  const fontSize = (node.isAggregate ? 11 : 9) / globalScale;
  const color = NODE_COLORS[node.type] || '#6B7280';
  const size = (node.isAggregate ? Math.min(18 + node.count / 40, 38) : (NODE_SIZES[node.type] || 7)) / globalScale;

  // Glow
  ctx.beginPath();
  ctx.arc(node.x, node.y, size + 3, 0, 2 * Math.PI);
  ctx.fillStyle = `${color}22`;
  ctx.fill();

  // Node body
  ctx.beginPath();
  ctx.arc(node.x, node.y, size, 0, 2 * Math.PI);
  ctx.fillStyle = color;
  ctx.fill();

  // Aggregate ring
  if (node.isAggregate) {
    ctx.beginPath();
    ctx.arc(node.x, node.y, size + 4, 0, 2 * Math.PI);
    ctx.strokeStyle = 'rgba(255,255,255,0.5)';
    ctx.lineWidth = 2 / globalScale;
    ctx.stroke();
  }

  // Border
  ctx.strokeStyle = 'rgba(255,255,255,0.2)';
  ctx.lineWidth = 1 / globalScale;
  ctx.stroke();

  // Label
  ctx.font = `${fontSize}px Inter, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillStyle = '#E5E7EB';
  ctx.fillText(label, node.x, node.y + size + 2);
}