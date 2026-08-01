import { useMemo } from 'react'
import katex from 'katex'
import 'katex/dist/katex.min.css'

interface FormulaProps {
  latex: string
  className?: string
}

export function Formula({ latex, className }: FormulaProps) {
  const html = useMemo(() => {
    try {
      return katex.renderToString(latex, {
        throwOnError: false,
        displayMode: false,
        strict: false,
      })
    } catch {
      return latex
    }
  }, [latex])

  return (
    <span
      className={className}
      style={{ display: 'block', overflowX: 'auto', overflowY: 'hidden', maxWidth: '100%' }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}
