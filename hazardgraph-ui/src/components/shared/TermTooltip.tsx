import type { ReactNode } from 'react'
import * as Tooltip from '@radix-ui/react-tooltip'
import { GLOSSARY } from '@/lib/glossary'
import { Formula } from '@/components/shared/Formula'
import { cn } from '@/lib/utils'

interface TermTooltipProps {
  term: string
  children?: ReactNode
  side?: 'top' | 'right' | 'bottom' | 'left'
  className?: string
}

export function TermTooltip({ term, children, side = 'bottom', className }: TermTooltipProps) {
  const entry = GLOSSARY[term]

  // If not in the glossary, just render the children (or the raw term) plainly.
  if (!entry) {
    return <>{children ?? term}</>
  }

  const trigger = children ?? (
    <span className="cursor-help border-b border-dotted border-risk-green/60 text-inherit">
      {term}
    </span>
  )

  return (
    <Tooltip.Provider delayDuration={120}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <span className={cn('inline-flex', className)}>{trigger}</span>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            side={side}
            sideOffset={6}
            className="z-[1200] max-w-xs rounded-lg border border-gray-700 bg-[#111827] p-3 text-sm text-white shadow-2xl"
          >
            {/* Term */}
            <div className="mb-1.5 font-semibold text-risk-green">{entry.term}</div>

            {/* Definition */}
            <div className="text-xs text-white">{entry.definition}</div>

            {/* Formula */}
            <div className="my-2 rounded-md bg-[#0A0F1E] px-2 py-1.5 text-center">
              <Formula latex={entry.formula} />
            </div>

            {/* IGAD context */}
            <div className="border-t border-gray-800 pt-1.5">
              <div className="mb-0.5 text-[10px] font-medium uppercase tracking-wide text-risk-green/80">
                IGAD context
              </div>
              <div className="text-[11px] leading-relaxed text-gray-300">{entry.igad}</div>
            </div>

            <Tooltip.Arrow className="fill-[#111827]" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  )
}