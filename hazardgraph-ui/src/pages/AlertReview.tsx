import { useState } from 'react';
import { useAlerts } from '../hooks/useAlerts';
import type { Alert } from '../hooks/useAlerts';
import { AlertQueueItem } from '../components/alerts/AlertQueueItem';
import { AlertApprovalDialog } from '../components/alerts/AlertApprovalDialog';
import { LoadingSpinner } from '../components/shared/LoadingSpinner';

export default function AlertReview() {
  const [statusFilter, setStatusFilter] = useState<string | undefined>('pending');
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);

  const { data: alerts, isLoading, error } = useAlerts(statusFilter);

  const pendingCount = (alerts as Alert[] | undefined)?.filter((a: Alert) => a.status === 'pending').length || 0;

  const filters = ['pending', 'approved', 'sent', 'rejected', undefined];

  return (
    <div className="flex h-screen flex-col bg-[#0A0F1E]">
      {/* Header */}
      <div className="border-b border-gray-800 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-['Raleway'] text-xl font-bold text-white">Alert Review</h1>
            <p className="text-sm text-gray-400">
              {pendingCount} pending approval
            </p>
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

        {!isLoading && !error && (!alerts || (alerts as Alert[]).length === 0) && (
          <div className="flex h-full items-center justify-center">
            <div className="text-center">
              <div className="mx-auto mb-3 flex h-16 w-16 items-center justify-center rounded-full bg-[#00C896]/10">
                <svg className="h-8 w-8 text-[#00C896]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <p className="text-gray-400">No alerts to review</p>
              <p className="mt-1 text-sm text-gray-500">
                All alerts have been processed
              </p>
            </div>
          </div>
        )}

        {!isLoading && (alerts as Alert[] | undefined) && (
          <div className="space-y-3">
            {(alerts as Alert[]).map((alert: Alert) => (
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