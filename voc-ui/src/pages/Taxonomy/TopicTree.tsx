import { useState, useMemo, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { useAppSelector } from '../../store/hooks'
import { selectFlatNodes, selectChildren, selectRootNodes } from '../../store/slices/taxonomySlice'
import TrendIndicator from '../../components/TrendIndicator/TrendIndicator'
import { MOCK_FEEDBACK_UNITS } from '../../store/mockData/feedbackUnits'
import type { RootState } from '../../store'
import type { TaxonomyNode } from '../../store/mockData/taxonomy'
import EmptyState from '../../components/EmptyState/EmptyState'

function TreeRow({
  node,
  depth,
  expanded,
  onToggle,
  hasChildren,
}: {
  node: TaxonomyNode
  depth: number
  expanded: boolean
  onToggle: () => void
  hasChildren: boolean
}) {
  const isUnclassified = node.status === 'candidate'

  return (
    <div
      className={`flex items-center gap-2 border-b border-slate-100 px-4 py-2.5 transition-colors hover:bg-slate-50 ${
        isUnclassified ? 'bg-amber-50/40' : ''
      }`}
      style={{ paddingLeft: `${16 + depth * 24}px` }}
    >
      {hasChildren ? (
        <button
          onClick={onToggle}
          className="flex h-5 w-5 shrink-0 items-center justify-center rounded text-slate-400 hover:bg-slate-200 hover:text-slate-600"
          aria-label={expanded ? 'Collapse' : 'Expand'}
        >
          <svg
            className={`h-3.5 w-3.5 transition-transform ${expanded ? 'rotate-90' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </button>
      ) : (
        <span className="w-5" />
      )}

      <Link
        to={`/taxonomy/${node.id}`}
        className="min-w-0 flex-1 text-sm font-medium text-slate-800 hover:text-primary-700"
      >
        {node.label}
      </Link>

      <span className="shrink-0 text-xs tabular-nums text-slate-500">{node.unitCount} units</span>
      <span className="w-16 shrink-0 text-right">
        <TrendIndicator trend={node.trend} />
      </span>

      {isUnclassified && (
        <Link
          to="/taxonomy/review"
          className="shrink-0 rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 hover:bg-amber-200"
        >
          Review
        </Link>
      )}
    </div>
  )
}

function TreeBranch({
  parentId,
  depth,
  expandedSet,
  onToggle,
  search,
}: {
  parentId: string | null
  depth: number
  expandedSet: Set<string>
  onToggle: (id: string) => void
  search: string
}) {
  const allNodes = useAppSelector(selectFlatNodes)
  const children = useAppSelector((state: RootState) => {
    if (parentId === null) return selectRootNodes(state)
    return selectChildren(state, parentId)
  })

  const matchesSearch = useCallback(
    (node: TaxonomyNode): boolean => {
      if (!search) return true
      if (node.label.toLowerCase().includes(search.toLowerCase())) return true
      const descendants = allNodes.filter((n) => n.parentId === node.id)
      return descendants.some((d) => matchesSearch(d))
    },
    [search, allNodes],
  )

  const filtered = children.filter(matchesSearch)

  return (
    <>
      {filtered.map((node) => {
        const nodeChildren = allNodes.filter((n) => n.parentId === node.id)
        const hasChildren = nodeChildren.length > 0
        const isExpanded = expandedSet.has(node.id) || (!!search && hasChildren)

        return (
          <div key={node.id}>
            <TreeRow
              node={node}
              depth={depth}
              expanded={isExpanded}
              onToggle={() => onToggle(node.id)}
              hasChildren={hasChildren}
            />
            {isExpanded && (
              <TreeBranch
                parentId={node.id}
                depth={depth + 1}
                expandedSet={expandedSet}
                onToggle={onToggle}
                search={search}
              />
            )}
          </div>
        )
      })}
    </>
  )
}

export default function TopicTree() {
  const [search, setSearch] = useState('')
  const [expandedSet, setExpandedSet] = useState<Set<string>>(new Set())

  const toggleExpanded = useCallback((id: string) => {
    setExpandedSet((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const allNodes = useAppSelector(selectFlatNodes)
  const totalTopics = useMemo(() => allNodes.filter((n) => n.status === 'active').length, [allNodes])
  const pendingReviewCount = useMemo(() => MOCK_FEEDBACK_UNITS.filter((u) => u.confidence < 0.70).length, [])

  const searchHasResults = useMemo(() => {
    if (!search) return true
    const q = search.toLowerCase()
    return allNodes.some((n) => n.label.toLowerCase().includes(q))
  }, [allNodes, search])

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-title">Taxonomy</h1>
          <p className="page-description">{totalTopics} active topics across the hierarchy</p>
        </div>
        <div className="flex items-center gap-2">
          {pendingReviewCount > 0 && (
            <Link to="/taxonomy/review" className="btn-secondary text-sm">
              Review Queue ({pendingReviewCount})
            </Link>
          )}
          <button className="btn-primary text-sm">+ Add topic</button>
          <Link to="/settings" className="btn-ghost text-sm">Settings</Link>
        </div>
      </div>

      <div className="mt-6">
        <input
          type="text"
          placeholder="Search topics…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input-base w-72"
        />
      </div>

      <div className="card mt-4 overflow-hidden">
        <div className="flex items-center gap-2 border-b border-slate-200 bg-slate-50 px-4 py-2 text-xs font-medium text-slate-500">
          <span className="w-5" />
          <span className="flex-1">Topic</span>
          <span>Units</span>
          <span className="w-16 text-right">Trend</span>
        </div>
        {searchHasResults ? (
          <TreeBranch
            parentId={null}
            depth={0}
            expandedSet={expandedSet}
            onToggle={toggleExpanded}
            search={search}
          />
        ) : (
          <div className="p-4">
            <EmptyState
              message="No topics match your search."
              actionLabel="Clear search"
              onAction={() => setSearch('')}
            />
          </div>
        )}
      </div>
    </div>
  )
}
