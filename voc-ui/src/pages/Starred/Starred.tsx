import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAppDispatch, useAppSelector } from '../../store/hooks'
import { selectAllCollections, createCollection, addToCollection, removeFromCollection } from '../../store/slices/starredSlice'
import { toggleStarUnit } from '../../store/slices/feedbackSlice'
import { selectAllAccounts, toggleStarAccount } from '../../store/slices/accountsSlice'
import { selectFlatNodes } from '../../store/slices/taxonomySlice'
import { MOCK_FEEDBACK_UNITS } from '../../store/mockData/feedbackUnits'
import SentimentBadge from '../../components/SentimentBadge/SentimentBadge'
import TrendIndicator from '../../components/TrendIndicator/TrendIndicator'
import EmptyState from '../../components/EmptyState/EmptyState'

type Tab = 'feedback' | 'accounts' | 'topics'

export default function Starred() {
  const dispatch = useAppDispatch()
  const collections = useAppSelector(selectAllCollections)
  const accounts = useAppSelector(selectAllAccounts)
  const topics = useAppSelector(selectFlatNodes)

  const [activeTab, setActiveTab] = useState<Tab>('feedback')
  const [selectedCollection, setSelectedCollection] = useState<string>('all')
  const [newCollectionName, setNewCollectionName] = useState('')
  const [showNewCollectionInput, setShowNewCollectionInput] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  const starredUnits = MOCK_FEEDBACK_UNITS.filter((u) => u.isStarred)
  const starredAccounts = accounts.filter((a) => a.isStarred)
  const trackedTopics = topics.filter((t) => t.status === 'active' && t.parentId === null)

  const displayedUnits = selectedCollection === 'all'
    ? starredUnits
    : (() => {
        const col = collections.find((c) => c.id === selectedCollection)
        return col ? starredUnits.filter((u) => col.unitIds.includes(u.id)) : []
      })()

  const handleCreateCollection = () => {
    if (newCollectionName.trim()) {
      dispatch(createCollection(newCollectionName.trim()))
      setNewCollectionName('')
      setShowNewCollectionInput(false)
    }
  }

  const handleExport = () => {
    setToast('Exported successfully')
    setTimeout(() => setToast(null), 2500)
  }

  const tabs: { value: Tab; label: string; count: number }[] = [
    { value: 'feedback', label: 'Starred Feedback', count: starredUnits.length },
    { value: 'accounts', label: 'Starred Accounts', count: starredAccounts.length },
    { value: 'topics', label: 'Tracked Topics', count: trackedTopics.length },
  ]

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-title">Starred</h1>
          <p className="page-description">Your saved feedback, accounts, and tracked topics</p>
        </div>
        <button onClick={handleExport} className="btn-secondary text-sm">
          Export
        </button>
      </div>

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 animate-fade-in rounded-lg bg-slate-900 px-4 py-2.5 text-sm text-white shadow-lg">
          {toast}
        </div>
      )}

      {/* Tabs */}
      <div className="mt-6 flex items-center gap-1 border-b border-slate-200">
        {tabs.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setActiveTab(tab.value)}
            className={`relative px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === tab.value
                ? 'text-primary-700 after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-primary-600'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            {tab.label}
            <span className="ml-1.5 rounded-full bg-slate-100 px-1.5 py-0.5 text-xs tabular-nums text-slate-600">{tab.count}</span>
          </button>
        ))}
      </div>

      {/* FEEDBACK TAB */}
      {activeTab === 'feedback' && (
        <div className="mt-6">
          {/* Collections bar */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => setSelectedCollection('all')}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                selectedCollection === 'all'
                  ? 'bg-primary-100 text-primary-700'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              All ({starredUnits.length})
            </button>
            {collections.map((col) => (
              <button
                key={col.id}
                onClick={() => setSelectedCollection(col.id)}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  selectedCollection === col.id
                    ? 'bg-primary-100 text-primary-700'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {col.name} ({col.unitIds.length})
              </button>
            ))}
            {showNewCollectionInput ? (
              <div className="flex items-center gap-1">
                <input
                  type="text"
                  value={newCollectionName}
                  onChange={(e) => setNewCollectionName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleCreateCollection()}
                  placeholder="Collection name"
                  className="input-base w-36 text-xs"
                  autoFocus
                />
                <button onClick={handleCreateCollection} className="text-xs text-primary-600 hover:underline">Add</button>
                <button onClick={() => setShowNewCollectionInput(false)} className="text-xs text-slate-400 hover:underline">Cancel</button>
              </div>
            ) : (
              <button
                onClick={() => setShowNewCollectionInput(true)}
                className="rounded-full border border-dashed border-slate-300 px-3 py-1 text-xs text-slate-500 hover:border-slate-400 hover:text-slate-700"
              >
                + New collection
              </button>
            )}
          </div>

          {/* Starred units list */}
          <div className="mt-4 space-y-3">
            {displayedUnits.map((u) => (
              <div key={u.id} className="card px-4 py-3">
                <div className="flex items-start gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-slate-800">{u.text}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <Link to={`/accounts/${u.accountId}`} className="text-xs text-slate-500 hover:text-primary-600">{u.accountName}</Link>
                      <span className="text-xs text-slate-400">{u.date}</span>
                      <span className="rounded-md bg-primary-50 px-1.5 py-0.5 text-xs font-medium text-primary-700">{u.topicLabel}</span>
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      <select
                        onChange={(e) => {
                          if (e.target.value) dispatch(addToCollection({ collectionId: e.target.value, unitId: u.id }))
                          e.target.value = ''
                        }}
                        className="input-base w-40 text-xs"
                        defaultValue=""
                      >
                        <option value="" disabled>+ Add to collection</option>
                        {collections.map((c) => (
                          <option key={c.id} value={c.id}>{c.name}</option>
                        ))}
                      </select>
                      {selectedCollection !== 'all' && (
                        <button
                          onClick={() => dispatch(removeFromCollection({ collectionId: selectedCollection, unitId: u.id }))}
                          className="text-xs text-red-500 hover:underline"
                        >
                          Remove
                        </button>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => dispatch(toggleStarUnit(u.id))}
                    className="shrink-0 text-lg text-amber-500"
                    aria-label="Unstar"
                  >
                    ★
                  </button>
                </div>
              </div>
            ))}
            {displayedUnits.length === 0 && (
              <EmptyState message="No starred feedback yet. Star items from the Explorer or Account pages." />
            )}
          </div>
        </div>
      )}

      {/* ACCOUNTS TAB */}
      {activeTab === 'accounts' && (
        <div className="mt-6 space-y-3">
          {starredAccounts.map((acct) => (
            <div key={acct.id} className="card flex items-center gap-4 px-4 py-3">
              <div className="min-w-0 flex-1">
                <Link to={`/accounts/${acct.id}`} className="text-sm font-medium text-slate-900 hover:text-primary-700">
                  {acct.name}
                </Link>
                <div className="mt-1 flex items-center gap-3 text-xs text-slate-500">
                  <span>{acct.unitCount} units</span>
                  <SentimentBadge polarity={acct.netSentiment} />
                  <span>{acct.segment}</span>
                </div>
              </div>
              <button onClick={() => dispatch(toggleStarAccount(acct.id))} className="text-lg text-amber-500" aria-label="Unstar">
                ★
              </button>
              <Link to={`/accounts/${acct.id}`} className="text-slate-400 hover:text-slate-600">
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </Link>
            </div>
          ))}
          {starredAccounts.length === 0 && (
            <EmptyState message="No starred accounts. Star accounts from the Accounts page." />
          )}
        </div>
      )}

      {/* TOPICS TAB */}
      {activeTab === 'topics' && (
        <div className="mt-6 space-y-3">
          {trackedTopics.map((t) => (
            <div key={t.id} className="card flex items-center gap-4 px-4 py-3">
              <div className="min-w-0 flex-1">
                <Link to={`/taxonomy/${t.id}`} className="text-sm font-medium text-slate-900 hover:text-primary-700">
                  {t.label}
                </Link>
                <div className="mt-1 flex items-center gap-3 text-xs text-slate-500">
                  <span>{t.unitCount} units</span>
                  <TrendIndicator trend={t.trend} />
                </div>
              </div>
              <Link to={`/taxonomy/${t.id}`} className="text-slate-400 hover:text-slate-600">
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                </svg>
              </Link>
            </div>
          ))}
          {trackedTopics.length === 0 && (
            <EmptyState message="No tracked topics. Topics will appear here as they are added to the taxonomy." />
          )}
        </div>
      )}
    </div>
  )
}
