import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { API_BASE_URL } from '@/lib/constants'
import { useAuth } from '@/hooks/useAuth'
import { TermTooltip } from '@/components/shared/TermTooltip'

interface NavLinkProps {
  href: string
  label: string
  active?: boolean
  badge?: number
}

function NavLink({ href, label, active, badge }: NavLinkProps) {
  const navigate = useNavigate()
  return (
    <button
      onClick={() => navigate(href)}
      className={cn(
        'relative px-3 py-2 text-sm font-medium transition-colors',
        active
          ? 'text-risk-green border-b-2 border-risk-green'
          : 'text-text-secondary hover:text-text-primary',
      )}
    >
      {label}
      {badge !== undefined && badge > 0 && (
        <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-risk-red px-1 text-[10px] font-bold text-white">
          {badge > 99 ? '99+' : badge}
        </span>
      )}
    </button>
  )
}

function formatEAT(date: Date): string {
  return date.toLocaleString('en-KE', {
    timeZone: 'Africa/Nairobi',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  })
}

export function QuantifayaHeader() {
  const [time, setTime] = useState(new Date())
  const [systemOk, setSystemOk] = useState(false)

  useEffect(() => {
    const interval = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/v1/ping`)
        setSystemOk(res.ok)
      } catch {
        setSystemOk(false)
      }
    }
    checkHealth()
    const healthInterval = setInterval(checkHealth, 30_000)
    return () => clearInterval(healthInterval)
  }, [])

  const currentPath = window.location.pathname

  return (
    <header className="flex items-center justify-between border-b border-border bg-[#0A0F1E] px-6 py-3">
      {/* Left: Brand */}
      <div className="flex items-center gap-2">
        <span className="text-xl font-bold text-white" style={{ fontFamily: 'Raleway, sans-serif', fontWeight: 700 }}>
          HazardGraph
        </span>
        <span className="text-sm text-risk-green" style={{ fontFamily: 'Raleway, sans-serif' }}>
          by Quantifaya
        </span>
      </div>

      {/* Centre: Nav — every item exposes a hover glossary tooltip */}
      <nav className="flex items-center gap-1">
        <TermTooltip term="Risk Score">
          <NavLink href="/" label="Dashboard" active={currentPath === '/'} />
        </TermTooltip>
        <TermTooltip term="Graph Explorer">
          <NavLink href="/graph" label="Graph Explorer" active={currentPath === '/graph'} />
        </TermTooltip>
        <TermTooltip term="Forecast & Analytics">
          <NavLink href="/analytics" label="Forecast & Analytics" active={currentPath === '/analytics'} />
        </TermTooltip>
        <TermTooltip term="Simulate & Run">
          <NavLink href="/scenarios" label="Simulate & Run" active={currentPath === '/scenarios'} />
        </TermTooltip>
        <TermTooltip term="Alert Review">
          <NavLink href="/alerts" label="Alert Review" />
        </TermTooltip>
      </nav>

      {/* Right: Clock + Status */}
      <div className="flex items-center gap-4">
        <span className="text-sm text-text-muted">{formatEAT(time)} EAT</span>
        <div className="flex items-center gap-1.5">
          <span
            className={cn(
              'h-2 w-2 rounded-full',
              systemOk ? 'bg-risk-green' : 'bg-risk-red',
            )}
          />
          <span className="text-xs text-text-muted">
            {systemOk ? 'System OK' : 'Degraded'}
          </span>
        </div>
      </div>
    </header>
  )
}