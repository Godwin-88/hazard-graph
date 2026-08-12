import { useEffect, useState } from 'react'
import { fetchJobErrors, type JobErrorLog } from '@/lib/api'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'

interface ErrorLogModalProps {
  runId: string
  jobName: string
  onClose: () => void
}

export function ErrorLogModal({ runId, jobName, onClose }: ErrorLogModalProps) {
  const [errors, setErrors] = useState<JobErrorLog[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetchJobErrors(runId)
        if (!cancelled) setErrors(res.errors)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load error details')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [runId])

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-xl border border-border bg-[#12172B] shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div>
            <h3 className="text-lg font-semibold text-white" style={{ fontFamily: 'Raleway, sans-serif' }}>
              Error Details
            </h3>
            <p className="text-xs text-text-secondary mt-0.5">
              {jobName.replace('_', ' ')} · <span className="font-mono text-risk-green">{runId.slice(0, 8)}</span>
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg border border-border px-3 py-1.5 text-sm text-text-secondary hover:text-white hover:border-risk-green/40 transition-colors"
          >
            Close
          </button>
        </div>

        {/* Body */}
        <div className="p-5">
          {loading && (
            <div className="flex items-center justify-center py-8">
              <LoadingSpinner />
            </div>
          )}

          {error && (
            <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-400">
              {error}
            </div>
          )}

          {!loading && !error && errors !== null && errors.length === 0 && (
            <div className="rounded-lg border border-border bg-[#0A0F1E] p-4 text-sm text-text-secondary">
              No structured error logs found for this run. The job may have failed before error capture, or the error
              message is only available in the job history.
            </div>
          )}

          {!loading && !error && errors !== null && errors.length > 0 && (
            <div className="space-y-4">
              {errors.map((e) => (
                <div key={e.id} className="rounded-lg border border-red-500/30 bg-[#0A0F1E] overflow-hidden">
                  {/* Error summary */}
                  <div className="flex items-center gap-2 border-b border-border/50 px-4 py-3">
                    <span className="rounded-full bg-red-500/15 px-2 py-0.5 text-xs font-medium text-red-400">
                      {e.error_type}
                    </span>
                    {e.node_name && (
                      <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-400">
                        node: {e.node_name}
                      </span>
                    )}
                    <span className="ml-auto text-xs text-text-secondary">
                      {e.created_at ? new Date(e.created_at).toLocaleString() : ''}
                    </span>
                  </div>

                  {/* Error message */}
                  <div className="px-4 py-3">
                    <p className="text-sm text-red-300 whitespace-pre-wrap">{e.error_message}</p>
                  </div>

                  {/* Traceback */}
                  {e.traceback && (
                    <details className="border-t border-border/50">
                      <summary className="cursor-pointer px-4 py-2 text-xs font-medium text-text-secondary hover:text-white transition-colors">
                        View full traceback
                      </summary>
                      <pre className="max-h-64 overflow-auto bg-black/40 px-4 py-3 text-xs leading-relaxed text-text-secondary whitespace-pre-wrap">
                        {e.traceback}
                      </pre>
                    </details>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}