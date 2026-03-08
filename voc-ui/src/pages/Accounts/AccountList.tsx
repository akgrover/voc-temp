import { useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useAppDispatch, useAppSelector } from '../../store/hooks'
import { selectAllAccounts, toggleStarAccount, type AccountSortBy } from '../../store/slices/accountsSlice'
import { SentimentBar } from '../../components/SentimentBadge/SentimentBadge'
import EmptyState from '../../components/EmptyState/EmptyState'

const sortOptions: { value: AccountSortBy; label: string }[] = [
  { value: 'most_recent', label: 'Most recent' },
  { value: 'most_units', label: 'Most feedback' },
  { value: 'worst_sentiment', label: 'Worst sentiment' },
  { value: 'alphabetical', label: 'A → Z' },
]

const segments = ['All', 'Enterprise', 'Mid-Market', 'Startup']

export default function AccountList() {
  const dispatch = useAppDispatch()
  const accounts = useAppSelector(selectAllAccounts)
  const [search, setSearch] = useState('')
  const [segment, setSegment] = useState('All')
  const [sortBy, setSortBy] = useState<AccountSortBy>('most_recent')

  const filtered = useMemo(() => {
    let list = [...accounts]
    if (search) list = list.filter((a) => a.name.toLowerCase().includes(search.toLowerCase()))
    if (segment !== 'All') list = list.filter((a) => a.segment === segment)

    const sortFns: Record<AccountSortBy, (a: typeof list[0], b: typeof list[0]) => number> = {
      most_units: (a, b) => b.unitCount - a.unitCount,
      worst_sentiment: (a, b) => a.netSentiment - b.netSentiment,
      most_recent: (a, b) => new Date(b.lastFeedbackDate).getTime() - new Date(a.lastFeedbackDate).getTime(),
      alphabetical: (a, b) => a.name.localeCompare(b.name),
    }
    list.sort(sortFns[sortBy])
    return list
  }, [accounts, search, segment, sortBy])

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <h1 className="page-title">Accounts</h1>
      <p className="page-description">Manage and explore customer accounts</p>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <input
          type="text"
          placeholder="Search accounts…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input-base w-64"
        />
        <select
          value={segment}
          onChange={(e) => setSegment(e.target.value)}
          className="input-base w-40"
        >
          {segments.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as AccountSortBy)}
          className="input-base w-44"
        >
          {sortOptions.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      <div className="mt-6 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="pb-3 pr-4 font-medium text-slate-500" />
              <th className="pb-3 pr-4 font-medium text-slate-500">Account</th>
              <th className="pb-3 pr-4 font-medium text-slate-500">Units</th>
              <th className="pb-3 pr-4 font-medium text-slate-500">Sentiment</th>
              <th className="pb-3 pr-4 font-medium text-slate-500">Top Topic</th>
              <th className="pb-3 pr-4 font-medium text-slate-500">Segment</th>
              <th className="pb-3 font-medium text-slate-500">Last Feedback</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filtered.map((acct) => (
              <tr key={acct.id} className="group transition-colors hover:bg-slate-50">
                <td className="py-3 pr-2">
                  <button
                    onClick={() => dispatch(toggleStarAccount(acct.id))}
                    className="text-lg leading-none"
                    aria-label={acct.isStarred ? 'Unstar' : 'Star'}
                  >
                    {acct.isStarred ? '★' : '☆'}
                  </button>
                </td>
                <td className="py-3 pr-4">
                  <Link to={`/accounts/${acct.id}`} className="font-medium text-slate-900 hover:text-primary-700">
                    {acct.name}
                  </Link>
                </td>
                <td className="py-3 pr-4 tabular-nums text-slate-600">{acct.unitCount}</td>
                <td className="py-3 pr-4">
                  <SentimentBar polarity={acct.netSentiment} />
                </td>
                <td className="py-3 pr-4 text-slate-600">{acct.topTopic}</td>
                <td className="py-3 pr-4 text-slate-500">{acct.segment ?? '—'}</td>
                <td className="py-3 text-slate-500">
                  {new Date(acct.lastFeedbackDate).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && accounts.length === 0 && (
          <div className="mt-4">
            <EmptyState message="No accounts found. Feedback data will populate accounts automatically." />
          </div>
        )}
        {filtered.length === 0 && accounts.length > 0 && (
          <div className="mt-4">
            <EmptyState
              message="No accounts match your search or filters."
              actionLabel="Reset filters"
              onAction={() => { setSearch(''); setSegment('All') }}
            />
          </div>
        )}
      </div>
    </div>
  )
}
