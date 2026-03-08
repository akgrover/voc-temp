import { useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  PieChart, Pie, Cell,
  ComposedChart, Line, Area,
} from 'recharts'
import { useAppSelector } from '../../store/hooks'
import { selectNodeById, selectChildren } from '../../store/slices/taxonomySlice'
import { MOCK_FEEDBACK_UNITS } from '../../store/mockData/feedbackUnits'
import type { IntentType } from '../../store/mockData/feedbackUnits'
import SentimentBadge from '../../components/SentimentBadge/SentimentBadge'
import TrendIndicator from '../../components/TrendIndicator/TrendIndicator'
import FeedbackUnitCard from '../../components/FeedbackUnitCard/FeedbackUnitCard'
import EmptyState from '../../components/EmptyState/EmptyState'

const INTENT_COLORS: Record<IntentType, string> = {
  bug_report: '#ef4444',
  feature_request: '#8b5cf6',
  praise: '#10b981',
  churn_signal: '#f59e0b',
  question: '#0ea5e9',
}
const INTENT_LABELS: Record<IntentType, string> = {
  bug_report: 'Bug',
  feature_request: 'Feature Request',
  praise: 'Praise',
  churn_signal: 'Churn Signal',
  question: 'Question',
}

const AI_SUMMARY_BY_TOPIC: Record<string, string> = {
  'tax-report-export': 'Report Export is the highest-volume topic, driven primarily by timeout errors on large files (10k+ rows) and format support requests (Excel vs PDF). Multiple enterprise accounts are affected, with Acme Corp being the most vocal. Recent improvements to the export queue system have been positively received.',
  'tax-login-fail': 'Login Failures surged after a recent deploy, primarily SSO-related. Globex Industries is at churn risk due to persistent login issues. MFA token rejections and slow password reset emails compound the problem. This is a critical topic requiring immediate engineering attention.',
  'tax-dashboard-load': 'Dashboard loading performance has been a mixed topic. Initial complaints about 12-second load times have been partially addressed — recent feedback praises the Feb update that reduced load to 2 seconds. Feature requests for loading skeletons and dark mode are also tagged here.',
  'tax-pricing': 'Pricing Concerns show a clear churn pattern. Umbrella Co and Globex Industries are explicitly comparing to competitors and threatening to leave. Per-seat pricing is the primary objection. This topic requires urgent attention from the pricing/retention team.',
}

export default function TopicDetail() {
  const { id } = useParams<{ id: string }>()
  const node = useAppSelector((state) => selectNodeById(state, id!))
  const children = useAppSelector((state) => selectChildren(state, id!))

  const topicUnits = useMemo(
    () => MOCK_FEEDBACK_UNITS.filter((u) => u.topicId === id).sort((a, b) => b.date.localeCompare(a.date)),
    [id],
  )

  const sentimentBuckets = useMemo(() => {
    const buckets = Array.from({ length: 10 }, (_, i) => ({
      range: `${(-1 + i * 0.2).toFixed(1)}`,
      count: 0,
    }))
    topicUnits.forEach((u) => {
      const idx = Math.min(Math.floor((u.sentiment.polarity + 1) / 0.2), 9)
      buckets[idx].count++
    })
    return buckets
  }, [topicUnits])

  const intentBreakdown = useMemo(() => {
    const counts: Record<string, number> = {}
    topicUnits.forEach((u) => {
      counts[u.intentType] = (counts[u.intentType] ?? 0) + 1
    })
    return Object.entries(counts).map(([type, count]) => ({
      type: type as IntentType,
      label: INTENT_LABELS[type as IntentType] ?? type,
      count,
    }))
  }, [topicUnits])

  const accountsMentioning = useMemo(() => {
    const map = new Map<string, { name: string; count: number; sentiment: number }>()
    topicUnits.forEach((u) => {
      const existing = map.get(u.accountId)
      if (existing) {
        existing.count++
        existing.sentiment = (existing.sentiment * (existing.count - 1) + u.sentiment.polarity) / existing.count
      } else {
        map.set(u.accountId, { name: u.accountName, count: 1, sentiment: u.sentiment.polarity })
      }
    })
    return [...map.entries()]
      .map(([accountId, data]) => ({ accountId, ...data }))
      .sort((a, b) => b.count - a.count)
  }, [topicUnits])

  const weeklyTrend = useMemo(() => {
    return Array.from({ length: 12 }, (_, i) => {
      const w = 12 - i
      const volume = Math.round(topicUnits.length / 4 + Math.random() * (topicUnits.length / 3))
      const sentiment = +(Math.random() * 2 - 1).toFixed(2)
      return { week: `W${w}`, volume, sentiment }
    }).reverse()
  }, [topicUnits.length])

  if (!node) {
    return (
      <div className="mx-auto max-w-7xl px-6 py-8">
        <EmptyState
          message="Topic not found."
          actionLabel="Back to Taxonomy"
          onAction={() => window.location.assign('/taxonomy')}
        />
      </div>
    )
  }

  const avgConfidence = node.confidenceAvg ?? 0

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <Link to="/taxonomy" className="text-sm text-primary-600 hover:underline">← Back to Taxonomy</Link>

      <div className="mt-3 flex items-center gap-3">
        <h1 className="page-title">{node.label}</h1>
        {node.status === 'candidate' && (
          <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-700">Candidate</span>
        )}
      </div>

      {/* Stats bar */}
      <div className="mt-4 flex flex-wrap items-center gap-6 text-sm text-slate-600">
        <span><strong className="text-slate-900">{node.unitCount}</strong> units</span>
        <span className="flex items-center gap-1">Trend: <TrendIndicator trend={node.trend} size="md" /></span>
        <span>Confidence: <strong className="text-slate-900">{(avgConfidence * 100).toFixed(0)}%</strong></span>
      </div>

      {/* Children */}
      {children.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {children.map((c) => (
            <Link
              key={c.id}
              to={`/taxonomy/${c.id}`}
              className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:border-primary-300 hover:text-primary-700"
            >
              {c.label} <span className="text-slate-400">({c.unitCount})</span>
            </Link>
          ))}
        </div>
      )}

      {/* AI Summary */}
      <div className="card mt-6 p-5">
        <h2 className="mb-2 text-sm font-semibold text-slate-800">AI Summary</h2>
        <p className="text-sm leading-relaxed text-slate-600">
          {AI_SUMMARY_BY_TOPIC[node.id] ?? `${node.label} has ${node.unitCount} feedback units with an average confidence of ${(avgConfidence * 100).toFixed(0)}%. Trending ${node.trend} over the last period.`}
        </p>
      </div>

      {/* Charts Row */}
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        {/* Sentiment Distribution */}
        <div className="card p-5">
          <h3 className="mb-3 text-sm font-semibold text-slate-800">Sentiment Distribution</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={sentimentBuckets}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="range" tick={{ fontSize: 10, fill: '#94a3b8' }} />
              <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} allowDecimals={false} />
              <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} />
              <Bar dataKey="count" fill="#6366f1" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Intent Breakdown */}
        <div className="card p-5">
          <h3 className="mb-3 text-sm font-semibold text-slate-800">Intent Breakdown</h3>
          {intentBreakdown.length > 0 ? (
            <div className="flex items-center gap-4">
              <ResponsiveContainer width={180} height={180}>
                <PieChart>
                  <Pie data={intentBreakdown} dataKey="count" nameKey="label" cx="50%" cy="50%" outerRadius={75} innerRadius={40}>
                    {intentBreakdown.map((entry) => (
                      <Cell key={entry.type} fill={INTENT_COLORS[entry.type]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-1.5">
                {intentBreakdown.map((entry) => (
                  <div key={entry.type} className="flex items-center gap-2 text-xs">
                    <span className="h-2.5 w-2.5 rounded-sm" style={{ background: INTENT_COLORS[entry.type] }} />
                    <span className="text-slate-700">{entry.label}</span>
                    <span className="text-slate-400">({entry.count})</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <EmptyState message="No intent data available." />
          )}
        </div>
      </div>

      {/* Accounts mentioning this topic */}
      <div className="mt-8">
        <h2 className="mb-4 text-lg font-semibold text-slate-900">Accounts Mentioning This Topic</h2>
        <div className="card overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50">
                <th className="px-4 py-2.5 font-medium text-slate-500">Account</th>
                <th className="px-4 py-2.5 font-medium text-slate-500">Units</th>
                <th className="px-4 py-2.5 font-medium text-slate-500">Avg Sentiment</th>
                <th className="px-4 py-2.5 font-medium text-slate-500" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {accountsMentioning.map((a) => (
                <tr key={a.accountId} className="hover:bg-slate-50">
                  <td className="px-4 py-2.5 font-medium text-slate-800">{a.name}</td>
                  <td className="px-4 py-2.5 tabular-nums text-slate-600">{a.count}</td>
                  <td className="px-4 py-2.5">
                    <SentimentBadge polarity={+a.sentiment.toFixed(2)} />
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <Link to={`/accounts/${a.accountId}`} className="text-xs text-primary-600 hover:underline">
                      View →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Verbatims */}
      <div className="mt-8">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">Sample Verbatims</h2>
          <Link
            to={`/explorer?topicId=${node.id}`}
            className="text-sm text-primary-600 hover:underline"
          >
            Show all {topicUnits.length} →
          </Link>
        </div>
        <div className="mt-4 space-y-3">
          {topicUnits.slice(0, 5).map((u) => (
            <FeedbackUnitCard key={u.id} unit={u} />
          ))}
        </div>
      </div>

      {/* Trend Chart */}
      <div className="card mt-8 p-5">
        <h3 className="mb-4 text-sm font-semibold text-slate-800">Volume & Sentiment Trend (12 weeks)</h3>
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={weeklyTrend}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="week" tick={{ fontSize: 11, fill: '#94a3b8' }} />
            <YAxis yAxisId="left" tick={{ fontSize: 11, fill: '#94a3b8' }} />
            <YAxis yAxisId="right" orientation="right" domain={[-1, 1]} tick={{ fontSize: 11, fill: '#94a3b8' }} />
            <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar yAxisId="left" dataKey="volume" name="Volume" fill="#6366f1" fillOpacity={0.7} radius={[3, 3, 0, 0]} />
            <Line yAxisId="right" type="monotone" dataKey="sentiment" name="Sentiment" stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} />
            <Area yAxisId="right" type="monotone" dataKey="sentiment" fill="#10b981" fillOpacity={0.05} stroke="none" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
