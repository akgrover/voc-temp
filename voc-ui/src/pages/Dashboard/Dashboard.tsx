import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  LineChart, Line, BarChart, Bar,
} from 'recharts'
import { useAppSelector } from '../../store/hooks'
import { selectFlatNodes } from '../../store/slices/taxonomySlice'
import { selectAllAccounts } from '../../store/slices/accountsSlice'
import { MOCK_SIGNALS } from '../../store/mockData/signals'
import { MOCK_FEEDBACK_UNITS } from '../../store/mockData/feedbackUnits'
import type { IntentType } from '../../store/mockData/feedbackUnits'
import TrendIndicator from '../../components/TrendIndicator/TrendIndicator'
import EmptyState from '../../components/EmptyState/EmptyState'

const weeklyTrendData = Array.from({ length: 12 }, (_, i) => {
  const w = 12 - i
  return {
    week: `W${w}`,
    bug_report: Math.round(18 + Math.random() * 14),
    feature_request: Math.round(12 + Math.random() * 10),
    praise: Math.round(8 + Math.random() * 8),
    churn_signal: Math.round(3 + Math.random() * 5),
    question: Math.round(4 + Math.random() * 4),
  }
}).reverse()

const intentColors: Record<IntentType, string> = {
  bug_report: '#ef4444',
  feature_request: '#8b5cf6',
  praise: '#10b981',
  churn_signal: '#f59e0b',
  question: '#0ea5e9',
}

const intentLabels: Record<IntentType, string> = {
  bug_report: 'Bug Report',
  feature_request: 'Feature Request',
  praise: 'Praise',
  churn_signal: 'Churn Signal',
  question: 'Question',
}

const ALL_INTENT_TYPES: IntentType[] = ['bug_report', 'feature_request', 'praise', 'churn_signal', 'question']

function generateTopicSparkline(topicId: string) {
  const seed = topicId.split('').reduce((s, c) => s + c.charCodeAt(0), 0)
  return Array.from({ length: 12 }, (_, i) => {
    const pseudo = Math.sin(seed * (i + 1)) * 0.5 + 0.5
    return {
      week: `W${i + 1}`,
      volume: Math.round(5 + pseudo * 20),
      sentiment: +((pseudo - 0.5) * 1.4).toFixed(2),
    }
  })
}

function KpiCard({ label, value, delta }: { label: string; value: string | number; delta?: string }) {
  return (
    <div className="card px-5 py-4">
      <p className="text-xs font-medium uppercase tracking-wider text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{value}</p>
      {delta && (
        <p className="mt-1">
          <TrendIndicator trend={delta} />
        </p>
      )}
    </div>
  )
}

function TopTopicsByType({ typeFilter }: { typeFilter: IntentType | 'all' }) {
  const nodes = useAppSelector(selectFlatNodes)
  const units = MOCK_FEEDBACK_UNITS
  const [sparklineKey, setSparklineKey] = useState<string | null>(null)

  const allTypes: { type: IntentType; label: string; color: string }[] = [
    { type: 'feature_request', label: 'Feature Request', color: 'bg-purple-50 border-purple-200' },
    { type: 'bug_report', label: 'Bug Report', color: 'bg-red-50 border-red-200' },
    { type: 'praise', label: 'Praise', color: 'bg-emerald-50 border-emerald-200' },
    { type: 'churn_signal', label: 'Churn Signal', color: 'bg-orange-50 border-orange-200' },
    { type: 'question', label: 'Question', color: 'bg-sky-50 border-sky-200' },
  ]
  const visibleTypes = typeFilter === 'all' ? allTypes : allTypes.filter((t) => t.type === typeFilter)

  const gridCols = visibleTypes.length === 1 ? 'sm:grid-cols-1' : 'sm:grid-cols-2'

  return (
    <div className={`grid gap-4 ${gridCols}`}>
      {visibleTypes.map(({ type, label, color }) => {
        const topicCounts = new Map<string, number>()
        units.filter((u) => u.intentType === type).forEach((u) => {
          topicCounts.set(u.topicId, (topicCounts.get(u.topicId) ?? 0) + 1)
        })
        const sorted = [...topicCounts.entries()]
          .sort((a, b) => b[1] - a[1])
          .slice(0, 5)

        return (
          <div key={type} className={`rounded-xl border p-4 ${color}`}>
            <h3 className="text-sm font-semibold text-slate-800">{label}</h3>
            <div className="mt-3 space-y-1">
              {sorted.map(([topicId, count]) => {
                const node = nodes.find((n) => n.id === topicId)
                const cardKey = `${type}:${topicId}`
                const isSparklineOpen = sparklineKey === cardKey

                return (
                  <div key={topicId}>
                    <div className="flex items-center justify-between rounded-md px-2 py-1 text-sm transition-colors hover:bg-white/60">
                      <Link
                        to={`/taxonomy/${topicId}`}
                        className="text-slate-700 hover:text-primary-700 hover:underline"
                      >
                        {node?.label ?? topicId}
                      </Link>
                      <span className="flex items-center gap-2">
                        <span className="text-xs tabular-nums text-slate-500">{count}</span>
                        {node && (
                          <button
                            onClick={() => setSparklineKey(isSparklineOpen ? null : cardKey)}
                            className="rounded p-0.5 transition-colors hover:bg-white/80"
                            title="Toggle sparkline"
                          >
                            <TrendIndicator trend={node.trend} />
                          </button>
                        )}
                      </span>
                    </div>

                    {isSparklineOpen && (
                      <div className="mx-2 mb-2 rounded-lg bg-white/80 p-3 shadow-sm">
                        <div className="grid gap-3 sm:grid-cols-2">
                          <div>
                            <p className="mb-1 text-[10px] font-medium uppercase tracking-wider text-slate-400">Volume (12 weeks)</p>
                            <ResponsiveContainer width="100%" height={60}>
                              <BarChart data={generateTopicSparkline(topicId)}>
                                <Bar dataKey="volume" fill={intentColors[type]} radius={[2, 2, 0, 0]} />
                                <Tooltip
                                  contentStyle={{ borderRadius: 6, fontSize: 10, padding: '4px 8px' }}
                                  labelStyle={{ fontSize: 10 }}
                                />
                              </BarChart>
                            </ResponsiveContainer>
                          </div>
                          <div>
                            <p className="mb-1 text-[10px] font-medium uppercase tracking-wider text-slate-400">Sentiment (12 weeks)</p>
                            <ResponsiveContainer width="100%" height={60}>
                              <LineChart data={generateTopicSparkline(topicId)}>
                                <Line type="monotone" dataKey="sentiment" stroke="#10b981" strokeWidth={1.5} dot={false} />
                                <Tooltip
                                  contentStyle={{ borderRadius: 6, fontSize: 10, padding: '4px 8px' }}
                                  labelStyle={{ fontSize: 10 }}
                                />
                              </LineChart>
                            </ResponsiveContainer>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
              {sorted.length === 0 && (
                <div className="py-2">
                  <EmptyState message="No feedback for this type yet." />
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function TopicTrendChart() {
  return (
    <div className="card p-5">
      <h3 className="mb-4 text-sm font-semibold text-slate-800">Topic Volume by Type (12 weeks)</h3>
      <ResponsiveContainer width="100%" height={280}>
        <AreaChart data={weeklyTrendData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="week" tick={{ fontSize: 11, fill: '#94a3b8' }} />
          <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} />
          <Tooltip
            contentStyle={{ borderRadius: 8, fontSize: 12, borderColor: '#e2e8f0' }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {(Object.keys(intentColors) as IntentType[]).map((type) => (
            <Area
              key={type}
              type="monotone"
              dataKey={type}
              name={intentLabels[type]}
              stackId="1"
              fill={intentColors[type]}
              stroke={intentColors[type]}
              fillOpacity={0.6}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

function SignalsPanel() {
  const severityDot: Record<string, string> = {
    red: 'bg-red-500',
    yellow: 'bg-amber-400',
    green: 'bg-emerald-500',
  }

  return (
    <div className="card">
      <div className="border-b border-slate-100 px-5 py-3">
        <h3 className="text-sm font-semibold text-slate-800">Active Signals</h3>
      </div>
      <div className="divide-y divide-slate-100">
        {MOCK_SIGNALS.map((s) => (
          <Link
            key={s.id}
            to={`/explorer?topicId=${s.topicId}&from=${s.date}`}
            className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-slate-50"
          >
            <span className={`h-2 w-2 shrink-0 rounded-full ${severityDot[s.severity]}`} />
            <div className="min-w-0 flex-1">
              <p className="text-sm text-slate-800">{s.message}</p>
              <p className="text-xs text-slate-400">{s.accountCount} accounts · {s.date}</p>
            </div>
            <svg className="h-4 w-4 shrink-0 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
          </Link>
        ))}
      </div>
    </div>
  )
}

function buildCsvContent(
  nodes: ReturnType<typeof selectFlatNodes>,
  units: typeof MOCK_FEEDBACK_UNITS,
  typeFilter: IntentType | 'all',
) {
  const types: IntentType[] = typeFilter === 'all' ? ALL_INTENT_TYPES : [typeFilter]
  const rows: string[][] = [['Intent Type', 'Topic', 'Units', 'Trend']]

  types.forEach((type) => {
    const topicCounts = new Map<string, number>()
    units.filter((u) => u.intentType === type).forEach((u) => {
      topicCounts.set(u.topicId, (topicCounts.get(u.topicId) ?? 0) + 1)
    })
    ;[...topicCounts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .forEach(([topicId, count]) => {
        const node = nodes.find((n) => n.id === topicId)
        rows.push([intentLabels[type], node?.label ?? topicId, String(count), node?.trend ?? ''])
      })
  })

  return rows.map((r) => r.map((c) => `"${c}"`).join(',')).join('\n')
}

export default function Dashboard() {
  const nodes = useAppSelector(selectFlatNodes)
  const accounts = useAppSelector(selectAllAccounts)
  const units = MOCK_FEEDBACK_UNITS
  const [typeFilter, setTypeFilter] = useState<IntentType | 'all'>('all')

  const avgSentiment = units.reduce((sum, u) => sum + u.sentiment.polarity, 0) / units.length

  const handleExportCsv = () => {
    const csv = buildCsvContent(nodes, units, typeFilter)
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'dashboard-topics.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  if (units.length === 0) {
    return (
      <div className="mx-auto max-w-7xl px-6 py-8">
        <h1 className="page-title">Dashboard</h1>
        <p className="page-description">Voice of Customer overview</p>
        <div className="mt-12">
          <EmptyState message="No feedback data yet. Connect a feedback source to get started." />
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <h1 className="page-title">Dashboard</h1>
      <p className="page-description">Voice of Customer overview</p>

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Topics" value={nodes.filter((n) => n.status === 'active').length} delta="+3" />
        <KpiCard label="Net Sentiment" value={avgSentiment > 0 ? `+${avgSentiment.toFixed(2)}` : avgSentiment.toFixed(2)} delta="-0.05" />
        <KpiCard label="Active Accounts" value={accounts.length} delta="+2" />
        <KpiCard label="Signals" value={MOCK_SIGNALS.length} delta="+1" />
      </div>

      <div className="mt-8">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">Top Topics by Intent Type</h2>
          <div className="flex items-center gap-2">
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value as IntentType | 'all')}
              className="input-base w-44 text-sm"
            >
              <option value="all">All types</option>
              {ALL_INTENT_TYPES.map((t) => (
                <option key={t} value={t}>{intentLabels[t]}</option>
              ))}
            </select>
            <button onClick={handleExportCsv} className="btn-secondary text-sm">
              Export CSV
            </button>
          </div>
        </div>
        <TopTopicsByType typeFilter={typeFilter} />
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <TopicTrendChart />
        </div>
        <div>
          <SignalsPanel />
        </div>
      </div>
    </div>
  )
}
