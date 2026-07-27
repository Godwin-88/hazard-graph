import { cn } from '@/lib/utils'

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  label?: string
}

const sizeClasses = {
  sm: 'h-4 w-4 border-2',
  md: 'h-8 w-8 border-3',
  lg: 'h-12 w-12 border-4',
}

export function LoadingSpinner({ size = 'md', label }: LoadingSpinnerProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-2">
      <div
        className={cn(
          'animate-spin rounded-full border-t-transparent',
          'border-risk-green',
          sizeClasses[size],
        )}
      />
      {label && (
        <p className="text-sm text-text-secondary">{label}</p>
      )}
    </div>
  )
}