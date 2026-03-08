import { useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useAppDispatch, useAppSelector } from '../../store/hooks'
import {
  selectFilteredUnits,
  selectFeedbackFilters,
  setFilters,
  resetFilters,
  type SortBy,
} from '../../store/slices/feedbackSlice'
import { selectFlatNodes } from '../../store/slices/taxonomySlice'
import { selectAllAccounts } from '../../store/slices/accountsSlice'
import type { IntentType } from '../../store/mockData/feedbackUnits'
import FeedbackUnitCard from '../../components/FeedbackUnitCard/FeedbackUnitCard'
import EmptyState from '../../components/EmptyState/EmptyState'

const INTENT_OPTIONS: { value: IntentType; label: string; color: string }[] = [
  { value: 'bug_report', label: 'Bug', color: 'bg-red-100 text-red-700 border-red-300' },
  { value: 'feature_request', label: 'Feature Request', color: 'bg-purple-100 text-purple-700 border-purple-300' },
  { value: 'praise', label: 'Praise', color: 'bg-emerald-100 text-emerald-700 border-emerald-300' },
  { value: 'churn_signal', label: 'Churn Signal', color: 'bg-orange-100 text-orange-700 border-orange-300' },
  { value: 'question', label: 'Question', color: 'bg-sky-100 text-sky-700 border-sky-300' },
]

const SORT_OPTIONS: { value: SortBy; label: string }[] = [
  { value: 'most_recent', label: 'Most recent' },
  { value: 'oldest', label: 'Oldest' },
  { value: 'worst_sentiment', label: 'Worst sentiment' },
  { value: 'best_sentiment', label: 'Best sentiment' },
  { value: 'most_accounts', label: 'Most duplicates' },
]

export default function Explorer() {
  const dispatch = useAppDispatch()
  const [searchParams] = useSearchParams()
  const units = useAppSelector(selectFilteredUnits)
  const filters = useAppSelector(selectFeedbackFilters)
  const topics = useAppSelector(selectFlatNodes)
  const accounts = useAppSelector(selectAllAccounts)

  useEffect(() => {
    const topicId = searchParams.get('topicId')
    if (topicId) {
      dispatch(setFilters({ topicId }))
    }
  }, [searchParams, dispatch])

  const toggleIntent = (type: IntentType) => {
    const current = filters.intentTypes
    const next = current.includes(type) ? current.filter((t) => t !== type) : [...current, type]
    dispatch(setFilters({ intentTypes: next }))
  }

  const summaryStats = useMemo(() => {
    const uniqueAccounts = new Set(units.map((u) => u.accountId)).size
    const avgSentiment = units.length > 0
      ? units.reduce((s, u) => s + u.sentiment.polarity, 0) / units.length
      : 0
    const intentCounts: Record<string, number> = {}
    const topicCounts: Record<string, number> = {}
    units.forEach((u) => {
      intentCounts[u.intentType] = (intentCounts[u.intentType] ?? 0) + 1
      topicCounts[u.topicLabel] = (topicCounts[u.topicLabel] ?? 0) + 1
    })
    const topIntent = Object.entries(intentCounts).sort((a, b) => b[1] - a[1])[0]
    const topTopic = Object.entries(topicCounts).sort((a, b) => b[1] - a[1])[0]

    return { uniqueAccounts, avgSentiment, topIntent, topTopic }
  }, [units])

  const activeFilterCount = [
    filters.intentTypes.length > 0,
    filters.topicId,
    filters.accountId,
    filters.starredOnly,
    filters.sentimentRange,
  ].filter(Boolean).length

  return (
    <div className="mx-auto max-w-7xl px-6 pb-20 pt-8">
      <h1 className="page-title">Feedback Explorer</h1>
      <p className="page-description">Search, filter, and analyze feedback across all accounts and topics</p>

      <div className="mt-6 grid gap-6 lg:grid-cols-[280px_1fr]">
        {/* Filter Panel */}
        <aside className="space-y-5">
          <div className="card p-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-800">Filters</h3>
              {activeFilterCount > 0 && (
                <button onClick={() => dispatch(resetFilters())} className="text-xs text-primary-600 hover:underline">
                  Reset all
                </button>
              )}
            </div>

            {/* Intent Type chips */}
            <div className="mt-4">
              <label className="label-base">Type</label>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {INTENT_OPTIONS.map((opt) => {
                  const active = filters.intentTypes.includes(opt.value)
                  return (
                    <button
                      key={opt.value}
                      onClick={() => toggleIntent(opt.value)}
                      className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
                        active ? opt.color : 'border-slate-200 bg-white text-slate-500 hover:border-slate-300'
                      }`}
                    >
                      {opt.label}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Topic filter */}
            <div className="mt-4">
              <label className="label-base">Topic</label>
              <select
                value={filters.topicId ?? ''}
                onChange={(e) => dispatch(setFilters({ topicId: e.target.value || null }))}
                className="input-base mt-1"
              >
                <option value="">All topics</option>
                {topics
                  .filter((t) => t.parentId !== null)
                  .map((t) => (
                    <option key={t.id} value={t.id}>{t.label}</option>
                  ))}
              </select>
            </div>

            {/* Account filter */}
            <div className="mt-4">
              <label className="label-base">Account</label>
              <select
                value={filters.accountId ?? ''}
                onChange={(e) => dispatch(setFilters({ accountId: e.target.value || null }))}
                className="input-base mt-1"
              >
                <option value="">All accounts</option>
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
            </div>

            {/* Starred only toggle */}
            <div className="mt-4 flex items-center gap-2">
              <input
                type="checkbox"
                id="starred-only"
                checked={filters.starredOnly}
                onChange={(e) => dispatch(setFilters({ starredOnly: e.target.checked }))}
                className="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-500"
              />
              <label htmlFor="starred-only" className="text-sm text-slate-700">Starred only</label>
            </div>

            {/* Sentiment range */}
            <div className="mt-4">
              <label className="label-base">Sentiment range</label>
              <div className="mt-1 flex items-center gap-2">
                <input
                  type="number"
                  min={-1}
                  max={1}
                  step={0.1}
                  placeholder="-1"
                  value={filters.sentimentRange?.min ?? ''}
                  onChange={(e) => {
                    const min = parseFloat(e.target.value)
                    if (!isNaN(min)) {
                      dispatch(setFilters({ sentimentRange: { min, max: filters.sentimentRange?.max ?? 1 } }))
                    } else {
                      dispatch(setFilters({ sentimentRange: null }))
                    }
                  }}
                  className="input-base w-20 text-center"
                />
                <span className="text-xs text-slate-400">to</span>
                <input
                  type="number"
                  min={-1}
                  max={1}
                  step={0.1}
                  placeholder="1"
                  value={filters.sentimentRange?.max ?? ''}
                  onChange={(e) => {
                    const max = parseFloat(e.target.value)
                    if (!isNaN(max)) {
                      dispatch(setFilters({ sentimentRange: { min: filters.sentimentRange?.min ?? -1, max } }))
                    } else {
                      dispatch(setFilters({ sentimentRange: null }))
                    }
                  }}
                  className="input-base w-20 text-center"
                />
              </div>
            </div>
          </div>
        </aside>

        {/* Results */}
        <div>
          <div className="flex items-center justify-between">
            <p className="text-sm text-slate-600">
              <strong className="text-slate-900">{units.length}</strong> results
            </p>
            <select
              value={filters.sortBy}
              onChange={(e) => dispatch(setFilters({ sortBy: e.target.value as SortBy }))}
              className="input-base w-44"
            >
              {SORT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          <div className="mt-4 space-y-3">
            {units.map((u) => (
              <FeedbackUnitCard key={u.id} unit={u} />
            ))}
            {units.length === 0 && (
              activeFilterCount > 0 ? (
                <EmptyState
                  message="No feedback units match your filters."
                  actionLabel="Reset all filters"
                  onAction={() => dispatch(resetFilters())}
                />
              ) : (
                <EmptyState message="No feedback data yet." />
              )
            )}
          </div>
        </div>
      </div>

      {/* Summary bar — fixed to viewport bottom */}
      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-slate-200 bg-white/95 px-6 py-3 shadow-card backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-6 text-sm">
          <span className="text-slate-600">
            <strong className="text-slate-900">{units.length}</strong> units
          </span>
          <span className="text-slate-600">
            <strong className="text-slate-900">{summaryStats.uniqueAccounts}</strong> accounts
          </span>
          <span className="text-slate-600">
            Net sentiment: <strong className={summaryStats.avgSentiment >= 0 ? 'text-emerald-600' : 'text-red-600'}>
              {summaryStats.avgSentiment >= 0 ? '+' : ''}{summaryStats.avgSentiment.toFixed(2)}
            </strong>
          </span>
          {summaryStats.topIntent && (
            <span className="text-slate-600">
              Top type: <strong className="text-slate-900">{summaryStats.topIntent[0].replace('_', ' ')}</strong>
            </span>
          )}
          {summaryStats.topTopic && (
            <span className="text-slate-600">
              Top topic: <strong className="text-slate-900">{summaryStats.topTopic[0]}</strong>
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
