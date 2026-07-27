import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { API_BASE_URL } from '@/lib/constants'

interface NavLinkProps {
  href: string
  label: string
  active?: boolean
}

function NavLink({ href, label, active }: NavLinkProps) {
  return (
    <a
      href={href}
      className={cn(
        'px-3 py-2 text-sm font-medium transition-colors',
        active
          ? 'text-risk-green border-b-2 border-risk-green'
          : 'text-text-secondary hover:text-text-primary',
      )}
    >
      {label}
    </a>
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
        const res = await fetch(`${API_BASE_URL}/api/v1/health`)
        const data = await res.json()
        setSystemOk(data.status === 'ok' || data.status === 'healthy')
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

      {/* Centre: Nav */}
      <nav className="flex items-center gap-1">
        <NavLink href="/" label="Dashboard" active={currentPath === '/'} />
        <NavLink href="/graph" label="Graph Explorer" active={currentPath === '/graph'} />
        <NavLink href="/alerts" label="Alerts" />
        <NavLink href="/admin" label="Admin" />
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