import type { Alert } from '../../hooks/useAlerts';
import { RegimeBadge } from '../shared/RegimeBadge';

interface AlertQueueItemProps {
  alert: Alert;
  onClick: () => void;
}

function getConfidenceLabel(confidence: number): string {
  if (confidence >= 0.7) return 'High'
  if (confidence >= 0.4) return 'Medium'
  return 'Low'
}

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

export function AlertQueueItem({ alert, onClick }: AlertQueueItemProps) {
  const statusColors: Record<string, string> = {
    pending: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    approved: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    sent: 'bg-green-500/20 text-green-400 border-green-500/30',
    rejected: 'bg-red-500/20 text-red-400 border-red-500/30',
    dispatch_failed: 'bg-red-500/20 text-red-400 border-red-500/30',
  };

  const scoreColor = alert.risk_score_at_trigger > 70
    ? 'text-red-400'
    : alert.risk_score_at_trigger > 50
    ? 'text-amber-400'
    : 'text-green-400';

  const preview = alert.message_text.length > 80
    ? alert.message_text.slice(0, 80) + '...'
    : alert.message_text;

  return (
    <div
      onClick={onClick}
      className="cursor-pointer rounded-lg border border-gray-800 bg-[#111827] p-4 transition-colors hover:border-gray-700 hover:bg-[#1a2235]"
    >
      <div className="flex items-start gap-4">
        {/* Left: region info */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="font-semibold text-white">
              {alert.region_name || alert.region_id}
            </h3>
            {alert.country && (
              <span className="text-xs text-gray-500">{alert.country}</span>
            )}
            {alert.current_regime && (
              <RegimeBadge regime={alert.current_regime} />
            )}
            {alert.confidence != null && (
              <span className={`rounded-full border px-1.5 py-0.5 text-[10px] font-medium ${getConfidenceColor(getConfidenceLabel(alert.confidence))}`}>
                {getConfidenceLabel(alert.confidence)}
              </span>
            )}
          </div>
          <p className="text-sm text-gray-400">{preview}</p>
        </div>

        {/* Right: metrics */}
        <div className="flex flex-col items-end gap-2 shrink-0">
          {/* Score */}
          <span className={`text-lg font-bold ${scoreColor}`}>
            {alert.risk_score_at_trigger.toFixed(0)}
            <span className="text-xs text-gray-500">/100</span>
          </span>

          {/* Kelly priority */}
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-text-muted">Kelly</span>
            <span className={`text-sm ${getKellyColor(alert.kelly_priority)}`}>
              {alert.kelly_priority.toFixed(3)}
            </span>
          </div>

          {/* Kelly bar */}
          <div className="w-16 h-1.5 rounded-full bg-gray-700 overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-[#0F4C81] to-[#00C896]"
              style={{ width: `${Math.min(alert.kelly_priority * 100, 100).toFixed(0)}%` }}
            />
          </div>

          {/* Status badge */}
          <span
            className={`rounded-full border px-2 py-0.5 text-xs font-medium ${
              statusColors[alert.status] || 'bg-gray-500/20 text-gray-400 border-gray-500/30'
            }`}
          >
            {alert.status}
          </span>
        </div>
      </div>
    </div>
  );
}