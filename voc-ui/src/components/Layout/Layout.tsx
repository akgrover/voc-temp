import { useState, useRef, useEffect } from 'react'
import { Outlet, NavLink, Link } from 'react-router-dom'
import { useAppDispatch, useAppSelector } from '../../store/hooks'
import {
  setGlobalSearch,
  setDateRange,
  toggleNotificationBell,
  closeNotificationBell,
  selectGlobalSearch,
  selectDateRange,
  selectNotificationBellOpen,
  type DateRangePreset,
} from '../../store/slices/uiSlice'
import { MOCK_SIGNALS } from '../../store/mockData/signals'
import { MOCK_TAXONOMY } from '../../store/mockData/taxonomy'
import { MOCK_ACCOUNTS } from '../../store/mockData/accounts'
import { MOCK_FEEDBACK_UNITS } from '../../store/mockData/feedbackUnits'

const navItems = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/accounts', label: 'Accounts' },
  { to: '/taxonomy', label: 'Taxonomy' },
  { to: '/explorer', label: 'Explorer' },
  { to: '/starred', label: 'Starred' },
] as const

const reviewCount = MOCK_FEEDBACK_UNITS.filter((u) => u.confidence < 0.70).length

const datePresets: { value: DateRangePreset; label: string }[] = [
  { value: '7d', label: '7 days' },
  { value: '30d', label: '30 days' },
  { value: '90d', label: '90 days' },
]

function severityDot(severity: 'red' | 'yellow' | 'green') {
  const colors = { red: 'bg-red-500', yellow: 'bg-amber-400', green: 'bg-emerald-500' }
  return <span className={`inline-block h-2 w-2 rounded-full ${colors[severity]}`} />
}

function GlobalSearchOverlay({ query, onClose }: { query: string; onClose: () => void }) {
  const q = query.toLowerCase()
  const topics = MOCK_TAXONOMY.filter((n) => n.label.toLowerCase().includes(q)).slice(0, 4)
  const accounts = MOCK_ACCOUNTS.filter((a) => a.name.toLowerCase().includes(q)).slice(0, 4)
  const units = MOCK_FEEDBACK_UNITS.filter((u) => u.text.toLowerCase().includes(q)).slice(0, 4)

  if (!topics.length && !accounts.length && !units.length) {
    return (
      <div className="absolute left-0 right-0 top-full z-50 mt-1 rounded-xl border border-slate-200 bg-white p-4 shadow-modal">
        <p className="text-sm text-slate-500">No results for "{query}"</p>
      </div>
    )
  }

  return (
    <div className="absolute left-0 right-0 top-full z-50 mt-1 rounded-xl border border-slate-200 bg-white shadow-modal">
      {topics.length > 0 && (
        <div className="border-b border-slate-100 p-3">
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">Topics</p>
          {topics.map((t) => (
            <Link
              key={t.id}
              to={`/taxonomy/${t.id}`}
              onClick={onClose}
              className="block rounded-md px-2 py-1.5 text-sm text-slate-700 hover:bg-primary-50 hover:text-primary-700"
            >
              {t.label} <span className="text-slate-400">· {t.unitCount} units</span>
            </Link>
          ))}
        </div>
      )}
      {accounts.length > 0 && (
        <div className="border-b border-slate-100 p-3">
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">Accounts</p>
          {accounts.map((a) => (
            <Link
              key={a.id}
              to={`/accounts/${a.id}`}
              onClick={onClose}
              className="block rounded-md px-2 py-1.5 text-sm text-slate-700 hover:bg-primary-50 hover:text-primary-700"
            >
              {a.name} <span className="text-slate-400">· {a.unitCount} units</span>
            </Link>
          ))}
        </div>
      )}
      {units.length > 0 && (
        <div className="p-3">
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">Feedback</p>
          {units.map((u) => (
            <Link
              key={u.id}
              to={`/explorer`}
              onClick={onClose}
              className="block rounded-md px-2 py-1.5 text-sm text-slate-700 hover:bg-primary-50 hover:text-primary-700"
            >
              <span className="line-clamp-1">{u.text}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}

function NotificationDropdown({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [onClose])

  return (
    <div
      ref={ref}
      className="absolute right-0 top-full z-50 mt-2 w-96 rounded-xl border border-slate-200 bg-white shadow-modal"
    >
      <div className="border-b border-slate-100 px-4 py-3">
        <p className="text-sm font-semibold text-slate-900">Notifications</p>
      </div>
      <div className="max-h-80 overflow-auto">
        {MOCK_SIGNALS.slice(0, 3).map((s) => (
          <Link
            key={s.id}
            to={`/explorer?topicId=${s.topicId}`}
            onClick={onClose}
            className="flex items-start gap-3 border-b border-slate-50 px-4 py-3 transition-colors hover:bg-slate-50"
          >
            <span className="mt-1.5">{severityDot(s.severity)}</span>
            <div className="min-w-0 flex-1">
              <p className="text-sm text-slate-800">{s.message}</p>
              <p className="mt-0.5 text-xs text-slate-400">{s.accountCount} accounts · {s.date}</p>
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}

export default function Layout() {
  const dispatch = useAppDispatch()
  const globalSearch = useAppSelector(selectGlobalSearch)
  const dateRange = useAppSelector(selectDateRange)
  const bellOpen = useAppSelector(selectNotificationBellOpen)

  const [searchFocused, setSearchFocused] = useState(false)
  const searchRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setSearchFocused(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const showSearchOverlay = searchFocused && globalSearch.length >= 2

  return (
    <div className="flex min-h-screen flex-col bg-surface">
      {/* Top bar */}
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/80">
        <div className="flex h-14 items-center gap-4 px-6">
          {/* Logo */}
          <Link to="/" className="flex shrink-0 items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-600 text-sm font-bold text-white">
              V
            </div>
            <span className="text-lg font-semibold tracking-tight text-slate-900">VoC</span>
          </Link>

          {/* Global search */}
          <div ref={searchRef} className="relative mx-auto w-full max-w-lg">
            <div className="relative">
              <svg
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input
                type="text"
                placeholder="Search feedback, topics, accounts…"
                value={globalSearch}
                onChange={(e) => dispatch(setGlobalSearch(e.target.value))}
                onFocus={() => setSearchFocused(true)}
                className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2 pl-10 pr-4 text-sm text-slate-700 placeholder-slate-400 transition-colors focus:border-primary-400 focus:bg-white focus:outline-none focus:ring-1 focus:ring-primary-400"
              />
            </div>
            {showSearchOverlay && (
              <GlobalSearchOverlay
                query={globalSearch}
                onClose={() => {
                  setSearchFocused(false)
                  dispatch(setGlobalSearch(''))
                }}
              />
            )}
          </div>

          {/* Date range */}
          <div className="flex shrink-0 items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 p-0.5">
            {datePresets.map((p) => (
              <button
                key={p.value}
                onClick={() => dispatch(setDateRange(p.value))}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                  dateRange === p.value
                    ? 'bg-white text-primary-700 shadow-sm'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          {/* Notification bell */}
          <div className="relative shrink-0">
            <button
              onClick={() => dispatch(toggleNotificationBell())}
              className="relative flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700"
              aria-label="Notifications"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0"
                />
              </svg>
              <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-red-500" />
            </button>
            {bellOpen && <NotificationDropdown onClose={() => dispatch(closeNotificationBell())} />}
          </div>

          {/* Help */}
          <button
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700"
            aria-label="Help"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z"
              />
            </svg>
          </button>

          {/* Settings */}
          <Link
            to="/settings"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700"
            aria-label="Settings"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z"
              />
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </Link>
        </div>

        {/* Nav tabs */}
        <nav className="flex items-center gap-1 px-6">
          {navItems.map(({ to, label, ...rest }) => (
            <NavLink
              key={to}
              to={to}
              end={'end' in rest ? rest.end : false}
              className={({ isActive }) =>
                `relative px-3 py-2.5 text-sm font-medium transition-colors ${
                  isActive
                    ? 'text-primary-700 after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:rounded-full after:bg-primary-600'
                    : 'text-slate-500 hover:text-slate-800'
                }`
              }
            >
              {label === 'Starred' ? `\u2605 ${label}` : label}
              {label === 'Taxonomy' && reviewCount > 0 && (
                <span className="ml-1.5 inline-flex h-4 min-w-[16px] items-center justify-center rounded-full bg-amber-100 px-1 text-[10px] font-semibold tabular-nums text-amber-700">
                  {reviewCount}
                </span>
              )}
            </NavLink>
          ))}
        </nav>
      </header>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
