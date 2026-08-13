import { useState, useEffect } from 'react';
import type { Alert } from '../../hooks/useAlerts';
import { useApproveAlert, useRejectAlert, useDispatchAlert } from '../../hooks/useAlerts';
import { RegimeBadge } from '../shared/RegimeBadge';
import { LoadingSpinner } from '../shared/LoadingSpinner';

interface AlertApprovalDialogProps {
  alert: Alert | null;
  onClose: () => void;
}

export function AlertApprovalDialog({ alert, onClose }: AlertApprovalDialogProps) {
  const approveMutation = useApproveAlert();
  const rejectMutation = useRejectAlert();
  const dispatchMutation = useDispatchAlert();

  const [messageText, setMessageText] = useState(alert?.message_text || '');
  const [langMode, setLangMode] = useState<'local' | 'english'>('local');
  const [rejectionReason, setRejectionReason] = useState('Inaccurate information');
  const [showRejectionInput, setShowRejectionInput] = useState(false);
  const [toast, setToast] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);

  useEffect(() => {
    setMessageText(alert?.message_text || '');
    setLangMode('local');
  }, [alert]);

  const switchLanguage = (mode: 'local' | 'english') => {
    if (!alert) return;
    const target = mode === 'english'
      ? (alert.english_text || alert.message_text)
      : alert.message_text;
    setMessageText(target);
    setLangMode(mode);
  };

  if (!alert) return null;

  const charCount = messageText.length;
  const charColor = charCount > 155 ? 'text-red-400' : charCount > 140 ? 'text-amber-400' : 'text-gray-400';

  const rejectionOptions = [
    'Inaccurate information',
    'Wrong language',
    'Tone inappropriate',
    'Risk level overstated',
    'Other',
  ];

  const showToast = (type: 'success' | 'error', msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 3000);
  };

  const handleApprove = async () => {
    try {
      await approveMutation.mutateAsync({ id: alert.id, messageText });
      showToast('success', 'Alert approved and queued');
      setTimeout(onClose, 1000);
    } catch {
      showToast('error', 'Failed to approve alert');
    }
  };

  const handleApproveAndDispatch = async () => {
    try {
      await approveMutation.mutateAsync({ id: alert.id, messageText });
      await dispatchMutation.mutateAsync(alert.id);
      showToast('success', 'Alert approved and dispatched');
      setTimeout(onClose, 1000);
    } catch {
      showToast('error', 'Failed to dispatch alert');
    }
  };

  const handleReject = async () => {
    try {
      await rejectMutation.mutateAsync({ id: alert.id, reason: rejectionReason });
      showToast('success', 'Alert rejected');
      setTimeout(onClose, 1000);
    } catch {
      showToast('error', 'Failed to reject alert');
    }
  };

  const handleRejectToggle = () => {
    if (showRejectionInput) {
      handleReject();
    } else {
      setShowRejectionInput(true);
    }
  };

  const components = alert.components || {};
  const sortedComps = Object.entries(components).sort(([, a], [, b]) => b - a).slice(0, 2);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="mx-4 w-full max-w-xl rounded-2xl border border-gray-800 bg-[#111827] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="border-b border-gray-800 px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-white">
                {alert.region_name || alert.region_id}
              </h2>
              <p className="text-sm text-gray-400">SMS Advisory Review</p>
            </div>
            {alert.current_regime && <RegimeBadge regime={alert.current_regime} />}
          </div>
        </div>

        <div className="space-y-6 px-6 py-5">
          {/* Language toggle */}
          <div className="flex items-center justify-center gap-2">
            <span className="text-xs text-gray-500">Preview language:</span>
            <div className="flex rounded-lg border border-gray-700 bg-gray-800 p-0.5">
              <button
                onClick={() => switchLanguage('local')}
                className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                  langMode === 'local'
                    ? 'bg-[#0F4C81] text-white'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                {alert.language.toUpperCase()}
              </button>
              <button
                onClick={() => switchLanguage('english')}
                className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                  langMode === 'english'
                    ? 'bg-[#0F4C81] text-white'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                ENGLISH
              </button>
            </div>
          </div>

          {/* Phone Preview */}
          <div className="flex justify-center">
            <div className="w-48 rounded-2xl border-2 border-gray-700 bg-[#0A0F1E] p-3">
              <div className="mb-1 text-center text-[10px] text-gray-500">SMS Preview</div>
              <div className="rounded-lg bg-[#1a3a5c] p-3">
                <p className="text-xs leading-relaxed text-white">{messageText}</p>
              </div>
              <div className={`mt-1 text-right text-xs ${charColor}`}>
                {charCount}/160
              </div>
            </div>
          </div>

          {/* Edit textarea */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-300">Edit Message</label>
            <textarea
              value={messageText}
              onChange={(e) => setMessageText(e.target.value.slice(0, 160))}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-[#0F4C81] focus:outline-none focus:ring-1 focus:ring-[#0F4C81]"
              rows={3}
              maxLength={160}
            />
            <div className={`text-right text-xs ${charColor}`}>
              {charCount}/160 characters
            </div>
          </div>

          {/* Context grid */}
          <div className="grid grid-cols-4 gap-3">
            <div className="rounded-lg bg-gray-800/50 p-2 text-center">
              <div className="text-xs text-gray-500">Score</div>
              <div className="text-sm font-bold text-white">{alert.risk_score_at_trigger.toFixed(0)}</div>
            </div>
            <div className="rounded-lg bg-gray-800/50 p-2 text-center">
              <div className="text-xs text-gray-500">Confidence</div>
              <div className="text-sm font-bold text-white">
                {alert.confidence ? `${(alert.confidence * 100).toFixed(0)}%` : 'N/A'}
              </div>
            </div>
            <div className="rounded-lg bg-gray-800/50 p-2 text-center">
              <div className="text-xs text-gray-500">Kelly</div>
              <div className="text-sm font-bold text-[#00C896]">
                {(alert.kelly_priority * 100).toFixed(1)}%
              </div>
            </div>
            <div className="rounded-lg bg-gray-800/50 p-2 text-center">
              <div className="text-xs text-gray-500">Language</div>
              <div className="text-sm font-bold text-white">{alert.language.toUpperCase()}</div>
            </div>
          </div>

          {/* Top risk drivers */}
          {sortedComps.length > 0 && (
            <div>
              <div className="mb-1 text-xs text-gray-500">Top risk drivers:</div>
              <div className="flex flex-wrap gap-2">
                {sortedComps.map(([key, val]) => (
                  <span
                    key={key}
                    className="rounded-full bg-gray-800 px-2 py-0.5 text-xs text-gray-300"
                  >
                    {key}: {(val * 100).toFixed(0)}%
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Toast */}
          {toast && (
            <div
              className={`rounded-lg px-4 py-2 text-sm ${
                toast.type === 'success'
                  ? 'bg-green-500/20 text-green-400'
                  : 'bg-red-500/20 text-red-400'
              }`}
            >
              {toast.msg}
            </div>
          )}

          {/* Rejection input */}
          {showRejectionInput && (
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-300">Reason for rejection</label>
              <select
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white"
              >
                {rejectionOptions.map((opt) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3">
            <button
              onClick={handleApprove}
              disabled={approveMutation.isPending}
              className="flex-1 rounded-lg bg-[#00C896] px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {approveMutation.isPending ? <LoadingSpinner size="sm" /> : 'Approve & Queue'}
            </button>
            <button
              onClick={handleApproveAndDispatch}
              disabled={approveMutation.isPending || dispatchMutation.isPending}
              className="flex-1 rounded-lg bg-[#0F4C81] px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {dispatchMutation.isPending ? <LoadingSpinner size="sm" /> : 'Dispatch Now'}
            </button>
            <button
              onClick={handleRejectToggle}
              disabled={rejectMutation.isPending}
              className="flex-1 rounded-lg bg-red-500/20 px-4 py-2 text-sm font-semibold text-red-400 hover:bg-red-500/30 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {showRejectionInput ? 'Confirm Reject' : 'Reject'}
            </button>
          </div>

          {showRejectionInput && (
            <button
              onClick={handleReject}
              disabled={rejectMutation.isPending}
              className="w-full rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:opacity-90"
            >
              {rejectMutation.isPending ? <LoadingSpinner size="sm" /> : `Confirm: ${rejectionReason}`}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}