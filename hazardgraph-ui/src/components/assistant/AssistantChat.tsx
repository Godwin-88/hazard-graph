import { useState, useRef, useEffect, Fragment } from 'react'
import type { ReactNode } from 'react'
import { sendAssistantMessage } from '@/lib/api'

/**
 * Minimal inline markdown renderer for assistant replies.
 * Supports **bold**, *italic*, and `inline code`. Everything else is
 * passed through as plain text (line breaks preserved).
 */
function renderInline(text: string): ReactNode[] {
  // Split on inline code first so we don't parse markdown inside code spans.
  const codeParts = text.split(/(`[^`]+`)/g)

  return codeParts.map((part, i) => {
    // Inline code span
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return (
        <code
          key={i}
          className="rounded bg-[#12172B] px-1.5 py-0.5 text-[11px] text-risk-green"
        >
          {part.slice(1, -1)}
        </code>
      )
    }

    // Bold + italic
    const boldParts = part.split(/(\*\*[^*]+\*\*)/g)
    return boldParts.map((boldPart, j) => {
      if (boldPart.startsWith('**') && boldPart.endsWith('**') && boldPart.length > 4) {
        return (
          <strong key={`${i}-${j}`} className="font-semibold text-white">
            {renderInline(boldPart.slice(2, -2))}
          </strong>
        )
      }

      // Italic
      const italicParts = boldPart.split(/(\*[^*]+\*)/g)
      return italicParts.map((italicPart, k) => {
        if (italicPart.startsWith('*') && italicPart.endsWith('*') && italicPart.length > 2) {
          return (
            <em key={`${i}-${j}-${k}`} className="italic text-gray-300">
              {italicPart.slice(1, -1)}
            </em>
          )
        }
        return <Fragment key={`${i}-${j}-${k}`}>{italicPart}</Fragment>
      })
    })
  })
}

interface Message {
  role: 'user' | 'assistant'
  content: string
}

export function AssistantChat() {
  const [open, setOpen] = useState(false)
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content:
        'Hello! I am the HazardGraph IGAD assistant. Ask me about risk scores, climate regimes, causal drivers, forecasts, or recommended actions.',
    },
  ])
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const send = async () => {
    const text = input.trim()
    if (!text || loading) return
    setMessages((m) => [...m, { role: 'user', content: text }])
    setInput('')
    setLoading(true)
    try {
      const res = await sendAssistantMessage(text, window.location.pathname)
      setMessages((m) => [...m, { role: 'assistant', content: res.reply }])
    } catch {
      setMessages((m) => [...m, { role: 'assistant', content: 'Could not reach the assistant. Please try again.' }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      {/* Floating toggle button */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="fixed bottom-5 right-5 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-risk-green text-[#0A0F1E] shadow-2xl hover:scale-105 transition-transform"
        aria-label="AI assistant"
      >
        <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
        </svg>
      </button>

      {/* Chat panel */}
      {open && (
        <div className="fixed bottom-24 right-5 z-50 flex h-[420px] w-[360px] flex-col overflow-hidden rounded-lg border border-gray-700 bg-[#0A0F1E] shadow-2xl">
          <div className="flex items-center justify-between border-b border-gray-800 bg-[#111827] px-4 py-2.5">
            <span className="text-sm font-semibold text-white">Quantifaya AI Assistant</span>
            <button onClick={() => setOpen(false)} className="text-xs text-gray-400 hover:text-white">
              Close
            </button>
          </div>

          <div className="flex-1 space-y-3 overflow-y-auto p-3">
            {messages.map((m, i) => (
              <div
                key={i}
                className={`max-w-[85%] rounded-lg px-3 py-2 text-xs leading-relaxed ${
                  m.role === 'user'
                    ? 'ml-auto bg-risk-green text-[#0A0F1E]'
                    : 'bg-[#12172B] text-gray-200'
                }`}
              >
                {m.role === 'assistant' ? renderInline(m.content) : m.content}
              </div>
            ))}
            {loading && <div className="max-w-[85%] rounded-lg bg-[#12172B] px-3 py-2 text-xs text-gray-400">Typing…</div>}
            <div ref={bottomRef} />
          </div>

          <div className="border-t border-gray-800 p-2">
            <div className="flex gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && send()}
                placeholder="Ask about risk, regimes, models…"
                className="flex-1 rounded-md bg-[#12172B] px-3 py-2 text-xs text-white placeholder-gray-500 border border-gray-700 outline-none focus:border-risk-green"
              />
              <button
                onClick={send}
                disabled={loading || !input.trim()}
                className="rounded-md bg-risk-green px-3 py-2 text-xs font-semibold text-[#0A0F1E] hover:opacity-80 disabled:opacity-40"
              >
                Send
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}