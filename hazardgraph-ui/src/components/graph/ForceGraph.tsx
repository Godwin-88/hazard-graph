import { useRef, useEffect, useCallback, useState } from 'react';

interface GraphNode {
  id: string;
  label: string;
  type: string;
  [key: string]: unknown;
}

interface GraphEdge {
  source: string;
  target: string;
  type: string;
  weight?: number;
  [key: string]: unknown;
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
};

const NODE_SIZES: Record<string, number> = {
  Region: 12,
  HazardRegime: 10,
};

export function ForceGraph({ nodes, edges, onNodeClick }: ForceGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [activeTypes, setActiveTypes] = useState<Set<string>>(new Set(Object.keys(NODE_COLORS)));
  const [minWeight, setMinWeight] = useState(0);
  const [graphReady, setGraphReady] = useState(false);

  // Dynamic import of ForceGraph2D
  useEffect(() => {
    let cancelled = false;
    import('react-force-graph-2d').then(() => {
      if (!cancelled) setGraphReady(true);
    }).catch(() => {
      if (!cancelled) setGraphReady(false);
    });
    return () => { cancelled = true; };
  }, []);

  // Filtered data
  const visibleNodes = nodes.filter((n) => activeTypes.has(n.type));
  const visibleEdges = edges
    .filter((e) => (e.weight ?? 1) >= minWeight);

  const graphData = {
    nodes: visibleNodes.map((n) => ({
      id: n.id,
      label: n.label,
      type: n.type,
      val: NODE_SIZES[n.type] || 6,
    })),
    links: visibleEdges.map((e) => ({
      source: e.source,
      target: e.target,
      type: e.type,
      weight: e.weight ?? 1,
    })),
  };

  const handleNodeClick = useCallback(
    (node: { id: string }) => {
      const found = nodes.find((n) => n.id === node.id);
      if (found && onNodeClick) onNodeClick(found);
    },
    [nodes, onNodeClick]
  );

  const nodeTypes = Object.keys(NODE_COLORS);

  // Simple canvas fallback render
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || graphReady) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = canvas.width;
    const h = canvas.height;

    ctx.fillStyle = '#0A0F1E';
    ctx.fillRect(0, 0, w, h);

    // Draw nodes as circles
    const positions = graphData.nodes.map((n, i) => {
      const angle = (2 * Math.PI * i) / graphData.nodes.length;
      const radius = Math.min(w, h) * 0.3;
      return {
        ...n,
        x: w / 2 + radius * Math.cos(angle),
        y: h / 2 + radius * Math.sin(angle),
      };
    });

    // Draw edges
    ctx.strokeStyle = '#4B5563';
    ctx.lineWidth = 1;
    graphData.links.forEach((link) => {
      const src = positions.find((n) => n.id === link.source);
      const tgt = positions.find((n) => n.id === link.target);
      if (src && tgt) {
        ctx.beginPath();
        ctx.moveTo(src.x, src.y);
        ctx.lineTo(tgt.x, tgt.y);
        ctx.stroke();
      }
    });

    // Draw nodes
    positions.forEach((node) => {
      const color = NODE_COLORS[node.type] || '#6B7280';
      const size = NODE_SIZES[node.type] || 6;

      ctx.beginPath();
      ctx.arc(node.x, node.y, size, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();

      // Label
      ctx.fillStyle = '#9CA3AF';
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(node.label, node.x, node.y + size + 12);
    });
  }, [graphData, graphReady]);

  return (
    <div className="relative h-full w-full">
      {/* Graph canvas */}
      <div ref={containerRef} className="h-full w-full">
        {graphReady ? (
          <ForceGraph2DWrapper
            graphData={graphData}
            onNodeClick={handleNodeClick}
          />
        ) : (
          <canvas
            ref={canvasRef}
            width={containerRef.current?.clientWidth || 800}
            height={containerRef.current?.clientHeight || 600}
            className="h-full w-full"
          />
        )}
      </div>

      {/* Controls overlay */}
      <div className="absolute top-4 right-4 space-y-3 rounded-lg border border-gray-800 bg-[#111827]/90 p-3 backdrop-blur-sm">
        {/* Type filter */}
        <div>
          <div className="mb-1 text-xs font-medium text-gray-400">Filter by type</div>
          <div className="space-y-1">
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
                  style={{ color: NODE_COLORS[type] || '#6B7280' }}
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

        {/* Stats */}
        <div className="text-xs text-gray-500">
          {visibleNodes.length} nodes, {visibleEdges.length} edges
        </div>
      </div>
    </div>
  );
}

// Separate wrapper to handle the dynamic import
function ForceGraph2DWrapper({
  graphData,
  onNodeClick,
}: {
  graphData: { nodes: { id: string; label: string; type: string; val: number }[]; links: { source: string; target: string; type: string; weight: number }[] };
  onNodeClick: (node: { id: string }) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [Component, setComponent] = useState<React.ComponentType<Record<string, unknown>> | null>(null);

  useEffect(() => {
    import('react-force-graph-2d').then((mod) => {
      setComponent(() => mod.default);
    }).catch(() => {
      setComponent(null);
    });
  }, []);

  useEffect(() => {
    if (!Component || !containerRef.current) return;

    const container = containerRef.current;
    const w = container.clientWidth || 800;
    const h = container.clientHeight || 600;

    // Render using the component
    const el = document.createElement('div');
    container.innerHTML = '';
    container.appendChild(el);

    // We use a simple canvas fallback since the types are complex
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    container.appendChild(canvas);

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.fillStyle = '#0A0F1E';
    ctx.fillRect(0, 0, w, h);

    const positions = graphData.nodes.map((n, i) => {
      const angle = (2 * Math.PI * i) / graphData.nodes.length;
      const radius = Math.min(w, h) * 0.3;
      return { ...n, x: w / 2 + radius * Math.cos(angle), y: h / 2 + radius * Math.sin(angle) };
    });

    graphData.links.forEach((link) => {
      const src = positions.find((n) => n.id === link.source);
      const tgt = positions.find((n) => n.id === link.target);
      if (src && tgt) {
        ctx.beginPath();
        ctx.moveTo(src.x, src.y);
        ctx.lineTo(tgt.x, tgt.y);
        ctx.strokeStyle = '#4B5563';
        ctx.stroke();
      }
    });

    positions.forEach((node) => {
      const color = NODE_COLORS[node.type] || '#6B7280';
      const size = NODE_SIZES[node.type] || 6;
      ctx.beginPath();
      ctx.arc(node.x, node.y, size, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.fillStyle = '#9CA3AF';
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(node.label, node.x, node.y + size + 12);
    });

    // Click handler
    const handleClick = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const clicked = positions.find((n) => {
        const dx = mx - n.x;
        const dy = my - n.y;
        return Math.sqrt(dx * dx + dy * dy) < 15;
      });
      if (clicked) onNodeClick({ id: clicked.id });
    };
    canvas.addEventListener('click', handleClick);
    return () => canvas.removeEventListener('click', handleClick);
  }, [Component, graphData, onNodeClick]);

  return <div ref={containerRef} className="h-full w-full" />;
}