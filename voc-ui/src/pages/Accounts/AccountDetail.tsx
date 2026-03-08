import { useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip,
  LineChart, Line, XAxis, YAxis, CartesianGrid,
} from 'recharts'
import { useAppDispatch, useAppSelector } from '../../store/hooks'
import { selectAccountById, toggleStarAccount } from '../../store/slices/accountsSlice'
import { MOCK_FEEDBACK_UNITS } from '../../store/mockData/feedbackUnits'
import SentimentBadge from '../../components/SentimentBadge/SentimentBadge'
import FeedbackUnitCard from '../../components/FeedbackUnitCard/FeedbackUnitCard'
import EmptyState from '../../components/EmptyState/EmptyState'

const AI_SUMMARY_BY_ACCOUNT: Record<string, string> = {
  'acct-1': 'Acme Corp is a high-value Enterprise account with significant feedback around Report Export issues, especially timeout errors on large files. They are also requesting Okta SSO and mobile offline capabilities. Sentiment is slightly negative, driven by export and onboarding friction, but recent interactions show improving support experience.',
  'acct-2': 'Globex Industries is at elevated churn risk. SSO login failures after a recent deploy are the primary driver of frustration, with multiple escalated tickets. Pricing concerns and slow support response are compounding the issue. Immediate attention on login stability is recommended.',
  'acct-3': 'Initech LLC is a satisfied Mid-Market account. They praise search speed improvements, bulk edit UX, and API documentation quality. No critical issues reported. Good candidate for a case study or referral.',
  'acct-4': 'Umbrella Co is showing strong churn signals around pricing — explicitly comparing to competitors and threatening to leave by renewal. Session timeout frustrations add to the negative sentiment. A proactive pricing discussion is strongly recommended.',
  'acct-5': 'TechStart Inc has a mixed profile. They appreciate onboarding improvements and export queue but are frustrated by login errors, CSV import issues, and outdated knowledge base articles. Net sentiment is neutral — the good experiences balance the bad.',
  'acct-6': 'Beta Labs is a happy Startup account. They love search speed, SSO integration, onboarding tutorials, and support responsiveness. Minor feature requests around scheduled exports and dark mode. Excellent retention outlook.',
}

const CONVERSATION_HISTORY = [
  { id: 'conv-1', source: 'Support Ticket #4421', summary: 'Report export timeout — escalated to engineering', date: '2026-02-22' },
  { id: 'conv-2', source: 'Quarterly Business Review', summary: 'Discussed roadmap priorities and renewal terms', date: '2026-02-15' },
  { id: 'conv-3', source: 'NPS Survey Response', summary: 'Score: 7 — mentioned export issues and SSO needs', date: '2026-02-10' },
  { id: 'conv-4', source: 'Intercom Chat', summary: 'Followed up on export workaround, resolved', date: '2026-02-18' },
]

const TOPIC_COLORS = ['#4f46e5', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#0ea5e9', '#ec4899', '#6366f1']

export default function AccountDetail() {
  const { id } = useParams<{ id: string }>()
  const dispatch = useAppDispatch()
  const account = useAppSelector((state) => selectAccountById(state, id!))

  const accountUnits = useMemo(
    () => MOCK_FEEDBACK_UNITS.filter((u) => u.accountId === id).sort((a, b) => b.date.localeCompare(a.date)),
    [id],
  )

  const topicBreakdown = useMemo(() => {
    const counts = new Map<string, { label: string; count: number }>()
    accountUnits.forEach((u) => {
      const existing = counts.get(u.topicId)
      if (existing) existing.count++
      else counts.set(u.topicId, { label: u.topicLabel, count: 1 })
    })
    return [...counts.values()].sort((a, b) => b.count - a.count)
  }, [accountUnits])

  const sentimentOverTime = useMemo(() => {
    const byWeek = new Map<string, number[]>()
    accountUnits.forEach((u) => {
      const week = u.date.slice(0, 7)
      const arr = byWeek.get(week) ?? []
      arr.push(u.sentiment.polarity)
      byWeek.set(week, arr)
    })
    return [...byWeek.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([week, pols]) => ({
        week,
        sentiment: +(pols.reduce((s, p) => s + p, 0) / pols.length).toFixed(2),
      }))
  }, [accountUnits])

  if (!account) {
    return (
      <div className="mx-auto max-w-7xl px-6 py-8">
        <EmptyState
          message="Account not found."
          actionLabel="Back to Accounts"
          onAction={() => window.location.assign('/accounts')}
        />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      {/* Back + Header */}
      <Link to="/accounts" className="text-sm text-primary-600 hover:underline">← Back to Accounts</Link>
      <div className="mt-3 flex items-center gap-3">
        <h1 className="page-title">{account.name}</h1>
        <button onClick={() => dispatch(toggleStarAccount(account.id))} className="text-xl">
          {account.isStarred ? '★' : '☆'}
        </button>
        {account.segment && (
          <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600">
            {account.segment}
          </span>
        )}
      </div>

      {/* Stats bar */}
      <div className="mt-4 flex flex-wrap items-center gap-6 text-sm text-slate-600">
        <span><strong className="text-slate-900">{accountUnits.length}</strong> feedback units</span>
        <span className="flex items-center gap-1">
          Net sentiment: <SentimentBadge polarity={account.netSentiment} size="md" />
        </span>
        <span>Last feedback: {new Date(account.lastFeedbackDate).toLocaleDateString()}</span>
      </div>

      {/* AI Summary */}
      <div className="card mt-6 p-5">
        <h2 className="mb-2 text-sm font-semibold text-slate-800">AI Summary</h2>
        <p className="text-sm leading-relaxed text-slate-600">
          {AI_SUMMARY_BY_ACCOUNT[account.id] ?? 'No AI summary available for this account.'}
        </p>
      </div>

      {/* Charts Row */}
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        {/* Topic Breakdown Pie */}
        <div className="card p-5">
          <h3 className="mb-3 text-sm font-semibold text-slate-800">Topic Breakdown</h3>
          {topicBreakdown.length > 0 ? (
            <div className="flex items-center gap-4">
              <ResponsiveContainer width={160} height={160}>
                <PieChart>
                  <Pie
                    data={topicBreakdown}
                    dataKey="count"
                    nameKey="label"
                    cx="50%"
                    cy="50%"
                    outerRadius={70}
                    innerRadius={35}
                  >
                    {topicBreakdown.map((_, i) => (
                      <Cell key={i} fill={TOPIC_COLORS[i % TOPIC_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-1">
                {topicBreakdown.map((t, i) => (
                  <div key={t.label} className="flex items-center gap-2 text-xs">
                    <span className="h-2.5 w-2.5 rounded-sm" style={{ background: TOPIC_COLORS[i % TOPIC_COLORS.length] }} />
                    <span className="text-slate-700">{t.label}</span>
                    <span className="text-slate-400">({t.count})</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-xs text-slate-400">No topic data available.</p>
          )}
        </div>

        {/* Sentiment Over Time */}
        <div className="card p-5">
          <h3 className="mb-3 text-sm font-semibold text-slate-800">Sentiment Over Time</h3>
          {sentimentOverTime.length > 1 ? (
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={sentimentOverTime}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="week" tick={{ fontSize: 11, fill: '#94a3b8' }} />
                <YAxis domain={[-1, 1]} tick={{ fontSize: 11, fill: '#94a3b8' }} />
                <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} />
                <Line type="monotone" dataKey="sentiment" stroke="#4f46e5" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-xs text-slate-400">Not enough data for a trend chart.</p>
          )}
        </div>
      </div>

      {/* Feedback Units */}
      <div className="mt-8">
        <h2 className="mb-4 text-lg font-semibold text-slate-900">Feedback Units ({accountUnits.length})</h2>
        {accountUnits.length > 0 ? (
          <div className="space-y-3">
            {accountUnits.map((u) => (
              <FeedbackUnitCard key={u.id} unit={u} />
            ))}
          </div>
        ) : (
          <EmptyState message="No feedback from this account yet." />
        )}
      </div>

      {/* Conversation History */}
      <div className="mt-8">
        <h2 className="mb-4 text-lg font-semibold text-slate-900">Conversation History</h2>
        <div className="card divide-y divide-slate-100">
          {CONVERSATION_HISTORY.map((c) => (
            <div key={c.id} className="flex items-center gap-4 px-5 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-slate-800">{c.source}</p>
                <p className="text-xs text-slate-500">{c.summary}</p>
              </div>
              <span className="shrink-0 text-xs tabular-nums text-slate-400">{c.date}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
