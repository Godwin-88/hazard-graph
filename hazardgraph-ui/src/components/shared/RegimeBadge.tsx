import { cn } from '@/lib/utils'

interface RegimeBadgeProps {
  regime: string
}

const regimeVariants: Record<string, string> = {
  Baseline: 'bg-gray-500 text-white',
  DroughtOnset: 'bg-amber-600 text-white',
  SevereDrought: 'bg-red-600 text-white animate-pulse',
  FloodWatch: 'bg-blue-600 text-white',
  FloodEmergency: 'bg-purple-600 text-white animate-pulse',
}

const defaultClass = 'bg-gray-500 text-white'

export function RegimeBadge({ regime }: RegimeBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
        regimeVariants[regime] ?? defaultClass,
      )}
    >
      {regime}
    </span>
  )
}