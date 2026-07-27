interface GraphNode {
  id: string;
  name: string;
  type: string;
  [key: string]: unknown;
}

interface NodeDetailSheetProps {
  node: GraphNode | null;
  onClose: () => void;
}

export function NodeDetailSheet({ node, onClose }: NodeDetailSheetProps) {
  if (!node) return null;

  const excludedKeys = ['id', 'name', 'type'];

  return (
    <div className="fixed inset-y-0 right-0 z-40 w-96 border-l border-gray-800 bg-[#111827] shadow-2xl transform transition-transform">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-800 px-4 py-3">
        <div>
          <h3 className="font-semibold text-white">{node.name || node.id}</h3>
          <span className="text-xs text-gray-400">{node.type}</span>
        </div>
        <button
          onClick={onClose}
          className="rounded-lg p-1 text-gray-400 hover:bg-gray-800 hover:text-white"
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Content */}
      <div className="overflow-y-auto p-4 space-y-4" style={{ maxHeight: 'calc(100vh - 60px)' }}>
        {Object.entries(node)
          .filter(([key]) => !excludedKeys.includes(key))
          .map(([key, value]) => (
            <div key={key} className="rounded-lg bg-gray-800/50 p-3">
              <div className="text-xs font-medium text-gray-500 mb-1">
                {key.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())}
              </div>
              <div className="text-sm text-white break-all">
                {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
              </div>
            </div>
          ))}

        {Object.keys(node).filter((k) => !excludedKeys.includes(k)).length === 0 && (
          <p className="text-sm text-gray-500 text-center">No additional properties</p>
        )}
      </div>
    </div>
  );
}