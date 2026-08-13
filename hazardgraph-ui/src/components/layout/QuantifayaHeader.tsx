import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { API_BASE_URL } from '@/lib/constants'
import { useAuth } from '@/hooks/useAuth'
import { useTheme } from '@/contexts/ThemeContext'
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
  const { theme, toggleTheme } = useTheme()

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
        <TermTooltip term="DataHub & Agent">
          <NavLink href="/datahub" label="DataHub & Agent" active={currentPath === '/datahub'} />
        </TermTooltip>
      </nav>

      {/* Right: Clock + Status + Theme toggle */}
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
        <button
          onClick={toggleTheme}
          title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-surface text-text-secondary transition-colors hover:text-text-primary"
        >
          {theme === 'dark' ? (
            /* Sun icon */
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
          ) : (
            /* Moon icon */
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
            </svg>
          )}
        </button>
      </div>
    </header>
  )
}