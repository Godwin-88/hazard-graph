import * as Dialog from '@radix-ui/react-dialog';
import { TermTooltip } from '@/components/shared/TermTooltip';

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
  lag_days?: number;
  [key: string]: unknown;
}

interface NodeDetailSheetProps {
  node: GraphNode | null;
  edges: GraphEdge[];
  nodesMap: Record<string, GraphNode>;
  onClose: () => void;
  onJumpTo: (nodeId: string) => void;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export function NodeDetailSheet({ node, edges, nodesMap, onClose, onJumpTo }: NodeDetailSheetProps) {
  if (!node) return null;

  const excludedKeys = ['id', 'label', 'type', 'properties'];
  const cleanProps: Record<string, unknown> = {};
  Object.entries(node).forEach(([k, v]) => { if (!excludedKeys.includes(k)) cleanProps[k] = v; });

  const relatedEdges = edges.filter(
    (e) => String(e.source) === String(node.id) || String(e.target) === String(node.id),
  );
  const propKeys = Object.keys(cleanProps);

  return (
    <Dialog.Root open={!!node} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(90vw,700px)] max-h-[85vh] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border border-gray-700 bg-[#111827] p-0 shadow-2xl">
          <div className="sticky top-0 flex items-center justify-between border-b border-gray-800 bg-[#111827] px-5 py-3">
            <div>
              <h3 className="font-semibold text-white">{node.label || node.id}</h3>
              <span className="text-xs text-risk-green">{node.type}</span>
            </div>
            <Dialog.Close asChild>
              <button className="rounded-lg p-1 text-gray-400 hover:bg-gray-800 hover:text-white">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </Dialog.Close>
          </div>

          <div className="space-y-5 p-5">

            {/* Properties */}
            <section>
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">Properties</h4>
              <div className="overflow-hidden rounded-lg border border-gray-800">
                <table className="w-full text-sm">
                  <tbody>
                    {propKeys.length === 0 && (
                      <tr><td className="px-3 py-3 text-center text-xs text-gray-500">No additional properties</td></tr>
                    )}
                    {propKeys.map((key) => (
                      <tr key={key} className="border-b border-gray-800 last:border-0">
                        <td className="w-2/5 bg-[#0A0F1E] px-3 py-2 align-top">
                          <TermTooltip term={key}>
                            <span className="text-xs font-medium text-gray-300">
                              {key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}
                            </span>
                          </TermTooltip>
                        </td>
                        <td className="px-3 py-2">
                          <span className="text-xs text-white break-all">{formatValue(cleanProps[key])}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            {/* Relationships */}
            <section>
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
                Relationships ({relatedEdges.length})
              </h4>
              {relatedEdges.length === 0 ? (
                <p className="text-xs text-gray-500">No relationships for this node</p>
              ) : (
                <div className="space-y-2">
                  {relatedEdges.map((e, i) => {
                    const isOutgoing = String(e.source) === String(node.id);
                    const otherId = String(isOutgoing ? e.target : e.source);
                    const other = nodesMap[otherId];
                    return (
                      <div key={i} className="flex items-center gap-2 rounded-md bg-[#0A0F1E] border border-gray-800 px-3 py-2">
                        <span className={`text-xs px-1.5 py-0.5 rounded border ${isOutgoing ? 'text-blue-300 border-blue-500/30' : 'text-purple-300 border-purple-500/30'}`}>
                          {isOutgoing ? 'out' : 'in'}
                        </span>
                        <button onClick={() => onJumpTo(otherId)} className="min-w-0 flex-1 text-left">
                          <span className="text-xs font-medium text-white truncate block">{other?.label || otherId}</span>
                          <span className="text-[10px] text-gray-500 block">{other?.type || 'node'}</span>
                        </button>
                        <span className="text-xs text-risk-green">{e.type}</span>
                        <span className="text-[10px] text-gray-500">w={e.weight?.toFixed(2) ?? '—'} lag={e.lag_days ?? 0}d</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>

          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
