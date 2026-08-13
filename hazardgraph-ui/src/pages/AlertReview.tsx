import { useMemo, useState } from 'react';
import { useAlerts, useGenerateAlerts } from '../hooks/useAlerts';
import type { Alert } from '../hooks/useAlerts';
import { AlertQueueItem } from '../components/alerts/AlertQueueItem';
import { AlertApprovalDialog } from '../components/alerts/AlertApprovalDialog';
import { LoadingSpinner } from '../components/shared/LoadingSpinner';
import { RegimeBadge } from '../components/shared/RegimeBadge';

function getConfidenceColor(confidence: string): string {
  switch (confidence) {
    case 'High': return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
    case 'Medium': return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
    case 'Low': return 'bg-red-500/20 text-red-400 border-red-500/30';
    default: return 'bg-gray-500/20 text-gray-400 border-gray-500/30';
  }
}

function getKellyColor(kelly: number): string {
  if (kelly > 0.5) return 'text-risk-red font-semibold';
  if (kelly > 0.2) return 'text-risk-amber';
  return 'text-text-muted';
}

export default function AlertReview() {
  const [statusFilter, setStatusFilter] = useState<string | undefined>('pending');
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  const [toast, setToast] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);

  // Fetch ALL alerts once and filter client-side. This guarantees the
  // pending tab always reflects the true pending count regardless of any
  // server-side status filter or React Query cache state.
  const { data: allAlerts, isLoading, error } = useAlerts();
  const generateMutation = useGenerateAlerts();

  const handleGenerate = async () => {
    try {
      const res = await generateMutation.mutateAsync();
      const count = (res as { generated_count?: number })?.generated_count ?? 0;
      setToast({ type: 'success', msg: `Generated ${count} new alert${count === 1 ? '' : 's'}` });
    } catch {
      setToast({ type: 'error', msg: 'Failed to generate alerts' });
    }
    setTimeout(() => setToast(null), 3000);
  };

  const alerts = useMemo(() => {
    const list = (allAlerts as Alert[] | undefined) ?? [];
    if (!statusFilter) return list;
    return list.filter((a: Alert) => a.status === statusFilter);
  }, [allAlerts, statusFilter]);

  const pendingCount = useMemo(
    () => ((allAlerts as Alert[] | undefined) ?? []).filter((a: Alert) => a.status === 'pending').length,
    [allAlerts],
  );

  const filters = ['pending', 'approved', 'sent', 'rejected', undefined];

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-gray-800 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-['Raleway'] text-xl font-bold text-white">Alert Review</h1>
            <p className="text-sm text-gray-400">
              {pendingCount} pending approval
            </p>
          </div>
          <div className="flex items-center gap-3">
            {toast && (
              <span
                className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
                  toast.type === 'success'
                    ? 'bg-green-500/20 text-green-400'
                    : 'bg-red-500/20 text-red-400'
                }`}
              >
                {toast.msg}
              </span>
            )}
            <button
              onClick={handleGenerate}
              disabled={generateMutation.isPending}
              className="flex items-center gap-2 rounded-lg bg-[#0F4C81] px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {generateMutation.isPending ? (
                <>
                  <LoadingSpinner size="sm" />
                  Generating...
                </>
              ) : (
                <>
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  Generate Alerts
                </>
              )}
            </button>
          </div>
        </div>

        {/* Filter tabs */}
        <div className="mt-4 flex gap-2">
          {filters.map((f) => (
            <button
              key={f ?? 'all'}
              onClick={() => setStatusFilter(f)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                statusFilter === f
                  ? 'bg-[#0F4C81] text-white'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}
            >
              {f ? f.charAt(0).toUpperCase() + f.slice(1) : 'All'}
            </button>
          ))}
        </div>
      </div>

      {/* Alert list */}
      <div className="flex-1 overflow-y-auto p-6">
        {isLoading && (
          <div className="flex h-full items-center justify-center">
            <LoadingSpinner size="lg" label="Loading alerts..." />
          </div>
        )}

        {error && (
          <div className="flex h-full items-center justify-center">
            <div className="text-center">
              <p className="text-red-400">Failed to load alerts</p>
              <p className="mt-1 text-sm text-gray-500">{(error as Error).message}</p>
            </div>
          </div>
        )}

        {!isLoading && !error && alerts.length === 0 && (
          <div className="flex h-full items-center justify-center">
            <div className="text-center">
              <div className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-full bg-[#00C896]/10">
                <svg className="h-8 w-8 text-[#00C896]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <p className="text-gray-400">No alerts to review</p>
              <p className="mt-1 text-sm text-gray-500">
                {statusFilter ? `No ${statusFilter} alerts` : 'All alerts have been processed'}
              </p>
            </div>
          </div>
        )}

        {!isLoading && alerts.length > 0 && (
          <div className="space-y-3">
            {alerts.map((alert: Alert) => (
              <AlertQueueItem
                key={alert.id}
                alert={alert}
                onClick={() => setSelectedAlert(alert)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Dialog */}
      <AlertApprovalDialog
        alert={selectedAlert}
        onClose={() => setSelectedAlert(null)}
      />
    </div>
  );
}