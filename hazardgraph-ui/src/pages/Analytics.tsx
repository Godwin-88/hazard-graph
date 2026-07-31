import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Legend,
} from 'recharts'
import { API_BASE_URL } from '@/lib/constants'

interface UptakeData {
  week: string
  yes_rate: number
  no_rate: number
}

interface RegionResponse {
  region: string
  sent: number
  responded: number
  yes_pct: number
  no_pct: number
  last_alert: string
}

interface LanguagePerf {
  language: string
  response_rate: number
  total_sent: number
}

interface AnalyticsData {
  total_alerts_30d: number
  overall_response_rate: number
  action_uptake_rate: number
  regions_in_alert: number
  weekly_uptake: UptakeData[]
  per_region: RegionResponse[]
  language_performance: LanguagePerf[]
}

function getAuthHeaders(): Record<string, string> {
  const token = sessionStorage.getItem('access_token');
  const headers: Record<string, string> = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

async function fetchAnalytics(): Promise<AnalyticsData> {
  const res = await fetch(`${API_BASE_URL}/api/v1/alerts/analytics/uptake`, {
    headers: getAuthHeaders(),
  })
  if (!res.ok) {
    // Return demo data if endpoint not available
    return getDemoAnalytics()
  }
  return res.json()
}

function getDemoAnalytics(): AnalyticsData {
  return {
    total_alerts_30d: 847,
    overall_response_rate: 62.4,
    action_uptake_rate: 58.3,
    regions_in_alert: 5,
    weekly_uptake: [
      { week: 'W22', yes_rate: 45.2, no_rate: 54.8 },
      { week: 'W23', yes_rate: 48.7, no_rate: 51.3 },
      { week: 'W24', yes_rate: 52.1, no_rate: 47.9 },
      { week: 'W25', yes_rate: 49.8, no_rate: 50.2 },
      { week: 'W26', yes_rate: 55.3, no_rate: 44.7 },
      { week: 'W27', yes_rate: 58.9, no_rate: 41.1 },
      { week: 'W28', yes_rate: 61.2, no_rate: 38.8 },
      { week: 'W29', yes_rate: 58.3, no_rate: 41.7 },
    ],
    per_region: [
      { region: 'Somalia', sent: 142, responded: 89, yes_pct: 41.5, no_pct: 58.5, last_alert: '2026-07-27' },
      { region: 'South Sudan', sent: 98, responded: 54, yes_pct: 36.7, no_pct: 63.3, last_alert: '2026-07-26' },
      { region: 'Ethiopia', sent: 187, responded: 112, yes_pct: 48.2, no_pct: 51.8, last_alert: '2026-07-27' },
      { region: 'Kenya', sent: 156, responded: 108, yes_pct: 62.0, no_pct: 38.0, last_alert: '2026-07-25' },
      { region: 'Sudan', sent: 73, responded: 48, yes_pct: 56.3, no_pct: 43.7, last_alert: '2026-07-24' },
      { region: 'Uganda', sent: 65, responded: 42, yes_pct: 66.7, no_pct: 33.3, last_alert: '2026-07-23' },
      { region: 'Tanzania', sent: 52, responded: 34, yes_pct: 70.6, no_pct: 29.4, last_alert: '2026-07-22' },
      { region: 'Djibouti', sent: 38, responded: 22, yes_pct: 52.3, no_pct: 47.7, last_alert: '2026-07-21' },
      { region: 'Eritrea', sent: 36, responded: 19, yes_pct: 47.4, no_pct: 52.6, last_alert: '2026-07-20' },
    ],
    language_performance: [
      { language: 'Swahili', response_rate: 64.2, total_sent: 320 },
      { language: 'Somali', response_rate: 48.7, total_sent: 185 },
      { language: 'Amharic', response_rate: 52.3, total_sent: 142 },
      { language: 'English', response_rate: 58.9, total_sent: 98 },
      { language: 'Arabic', response_rate: 43.1, total_sent: 67 },
    ],
  }
}

function getUptakeColor(rate: number): string {
  if (rate >= 60) return 'bg-emerald-500'
  if (rate >= 30) return 'bg-amber-500'
  return 'bg-red-500'
}

function getUptakeTextColor(rate: number): string {
  if (rate >= 60) return 'text-emerald-400'
  if (rate >= 30) return 'text-amber-400'
  return 'text-red-400'
}

export default function Analytics() {
  const [data, setData] = useState<AnalyticsData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchAnalytics()
      .then(setData)
      .catch(() => setData(getDemoAnalytics()))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-text-muted">
        Loading analytics...
      </div>
    )
  }

  if (!data) return null

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full" style={{ fontFamily: 'Inter, sans-serif' }}>
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white" style={{ fontFamily: 'Raleway, sans-serif', fontWeight: 700 }}>
          Community Response Analytics
        </h1>
        <p className="text-sm text-text-secondary mt-1">
          SMS feedback loop performance across all IGAD regions
        </p>
      </div>

      {/* Section 1 — Summary KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="bg-[#141B2D] border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-text-secondary font-medium">Total Alerts Sent</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold text-white">{data.total_alerts_30d.toLocaleString()}</p>
            <p className="text-xs text-text-secondary mt-1">Last 30 days</p>
          </CardContent>
        </Card>

        <Card className="bg-[#141B2D] border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-text-secondary font-medium">Response Rate</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold text-white">{data.overall_response_rate.toFixed(1)}%</p>
            <p className="text-xs text-text-secondary mt-1">of recipients replied</p>
          </CardContent>
        </Card>

        <Card className="bg-[#141B2D] border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-text-secondary font-medium">Action Uptake Rate</CardTitle>
          </CardHeader>
          <CardContent>
            <p className={`text-3xl font-bold ${getUptakeTextColor(data.action_uptake_rate)}`}>
              {data.action_uptake_rate.toFixed(1)}%
            </p>
            <p className="text-xs text-text-secondary mt-1">replied YES — took action</p>
          </CardContent>
        </Card>

        <Card className="bg-[#141B2D] border-border">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-text-secondary font-medium">Regions in Alert</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold text-white">{data.regions_in_alert}</p>
            <p className="text-xs text-text-secondary mt-1">current week</p>
          </CardContent>
        </Card>
      </div>

      {/* Section 2 — Weekly Uptake Trend */}
      <Card className="bg-[#141B2D] border-border">
        <CardHeader>
          <CardTitle className="text-white" style={{ fontFamily: 'Raleway, sans-serif' }}>
            Action Uptake Over Time
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={data.weekly_uptake}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2D3A5C" />
              <XAxis dataKey="week" stroke="#7B8DB8" />
              <YAxis stroke="#7B8DB8" domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1A2340', border: '1px solid #2D3A5C', borderRadius: '8px' }}
                formatter={(value: number) => [`${value.toFixed(1)}%`]}
              />
              <ReferenceLine y={50} stroke="#7B8DB8" strokeDasharray="5 5" label={{ value: '50% threshold', fill: '#7B8DB8' }} />
              <Line type="monotone" dataKey="yes_rate" stroke="#22C55E" strokeWidth={2} name="YES (took action)" dot={{ fill: '#22C55E', r: 4 }} />
              <Line type="monotone" dataKey="no_rate" stroke="#EF4444" strokeWidth={2} name="NO (did not act)" dot={{ fill: '#EF4444', r: 4 }} />
              <Legend />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {/* Section 3 — Per-Region Response Table */}
      <Card className="bg-[#141B2D] border-border">
        <CardHeader>
          <CardTitle className="text-white" style={{ fontFamily: 'Raleway, sans-serif' }}>
            Per-Region Response — Sorted by Lowest Uptake
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-text-secondary">
                  <th className="text-left py-3 px-2 font-medium">Region</th>
                  <th className="text-right py-3 px-2 font-medium">Sent</th>
                  <th className="text-right py-3 px-2 font-medium">Responded</th>
                  <th className="text-right py-3 px-2 font-medium">Y%</th>
                  <th className="text-right py-3 px-2 font-medium">N%</th>
                  <th className="text-right py-3 px-2 font-medium">Last Alert</th>
                </tr>
              </thead>
              <tbody>
                {[...data.per_region]
                  .sort((a, b) => a.yes_pct - b.yes_pct)
                  .map((row) => (
                    <tr
                      key={row.region}
                      className={`border-b border-border/50 ${
                        row.yes_pct < 30 ? 'bg-red-900/10' : ''
                      }`}
                    >
                      <td className="py-3 px-2 text-white font-medium">{row.region}</td>
                      <td className="py-3 px-2 text-right text-text-secondary">{row.sent}</td>
                      <td className="py-3 px-2 text-right text-text-secondary">{row.responded}</td>
                      <td className={`py-3 px-2 text-right font-medium ${
                        row.yes_pct < 30 ? 'text-red-400' : row.yes_pct >= 60 ? 'text-emerald-400' : 'text-amber-400'
                      }`}>
                        {row.yes_pct.toFixed(1)}%
                      </td>
                      <td className="py-3 px-2 text-right text-text-secondary">{row.no_pct.toFixed(1)}%</td>
                      <td className="py-3 px-2 text-right text-text-secondary">{row.last_alert}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Section 4 — Language Performance */}
      <Card className="bg-[#141B2D] border-border">
        <CardHeader>
          <CardTitle className="text-white" style={{ fontFamily: 'Raleway, sans-serif' }}>
            Language Engagement
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={data.language_performance}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2D3A5C" vertical={false} />
              <XAxis dataKey="language" stroke="#7B8DB8" />
              <YAxis stroke="#7B8DB8" domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1A2340', border: '1px solid #2D3A5C', borderRadius: '8px' }}
                formatter={(value: number, name: string) => [
                  `${value.toFixed(1)}%`,
                  name === 'response_rate' ? 'Response Rate' : 'Total Sent',
                ]}
              />
              <Bar dataKey="response_rate" fill="#22C55E" radius={[4, 4, 0, 0]} name="Response Rate" />
              <Legend />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </div>
  )
}