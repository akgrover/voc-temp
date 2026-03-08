import { useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useAppDispatch, useAppSelector } from '../../store/hooks'
import { selectFlatNodes, renameNode, mergeNodes } from '../../store/slices/taxonomySlice'
import { MOCK_FEEDBACK_UNITS } from '../../store/mockData/feedbackUnits'

type AlertRule = {
  id: string
  condition: string
  channel: string
}

const INITIAL_ALERT_RULES: AlertRule[] = [
  { id: 'rule-1', condition: 'Topic volume increases > 50% week-over-week', channel: 'Slack #voc-alerts' },
  { id: 'rule-2', condition: 'New churn signal detected from Enterprise account', channel: 'Email to CS team' },
  { id: 'rule-3', condition: 'Topic confidence drops below 70%', channel: 'Slack #ml-ops' },
]

export default function Settings() {
  const dispatch = useAppDispatch()
  const allNodes = useAppSelector(selectFlatNodes)

  const [thresholds, setThresholds] = useState({
    duplicate: 0.85,
    topicMatch: 0.75,
    newTopicFloor: 0.60,
  })
  const [alertRules, setAlertRules] = useState<AlertRule[]>(INITIAL_ALERT_RULES)
  const [topicSearch, setTopicSearch] = useState('')
  const [editingNode, setEditingNode] = useState<string | null>(null)
  const [editLabel, setEditLabel] = useState('')
  const [mergeTarget, setMergeTarget] = useState<string | null>(null)
  const [mergeInto, setMergeInto] = useState('')
  const [toast, setToast] = useState<string | null>(null)

  const reviewQueue = useMemo(
    () => MOCK_FEEDBACK_UNITS.filter((u) => u.confidence < 0.70).sort((a, b) => a.confidence - b.confidence),
    [],
  )

  const filteredNodes = useMemo(
    () => allNodes.filter((n) => n.label.toLowerCase().includes(topicSearch.toLowerCase())),
    [allNodes, topicSearch],
  )

  const showToast = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(null), 2500)
  }

  const handleRename = (nodeId: string) => {
    if (editLabel.trim()) {
      dispatch(renameNode({ id: nodeId, label: editLabel.trim() }))
      setEditingNode(null)
      setEditLabel('')
      showToast('Topic renamed')
    }
  }

  const handleMerge = (sourceId: string) => {
    if (mergeInto) {
      dispatch(mergeNodes({ sourceId, targetId: mergeInto }))
      setMergeTarget(null)
      setMergeInto('')
      showToast('Topics merged')
    }
  }

  const handleAddRule = () => {
    setAlertRules((prev) => [
      ...prev,
      { id: `rule-${Date.now()}`, condition: 'New rule — click to edit', channel: 'Slack' },
    ])
    showToast('Alert rule added')
  }

  const handleDeleteRule = (ruleId: string) => {
    setAlertRules((prev) => prev.filter((r) => r.id !== ruleId))
    showToast('Alert rule removed')
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <h1 className="page-title">Settings</h1>
      <p className="page-description">Manage taxonomy, review queue, thresholds, and alert rules</p>

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 animate-fade-in rounded-lg bg-slate-900 px-4 py-2.5 text-sm text-white shadow-lg">
          {toast}
        </div>
      )}

      {/* Review Queue Summary */}
      <section className="mt-8">
        <div className="card flex items-center gap-4 px-5 py-4">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-600">
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
            </svg>
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-slate-900">
              {reviewQueue.length} item{reviewQueue.length !== 1 ? 's' : ''} pending review
            </p>
            <p className="text-xs text-slate-500">Low-confidence feedback units that need manual classification</p>
          </div>
          <Link to="/taxonomy/review" className="btn-primary text-sm">
            Go to Review Queue
          </Link>
        </div>
      </section>

      {/* Topic Management */}
      <section className="mt-10">
        <h2 className="text-lg font-semibold text-slate-900">Topic Management</h2>
        <p className="mt-1 text-sm text-slate-500">Rename, merge, or reorganize topics</p>

        <input
          type="text"
          placeholder="Search topics…"
          value={topicSearch}
          onChange={(e) => setTopicSearch(e.target.value)}
          className="input-base mt-4 w-64"
        />

        <div className="card mt-4 overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50">
                <th className="px-4 py-2.5 font-medium text-slate-500">Topic</th>
                <th className="px-4 py-2.5 font-medium text-slate-500">Units</th>
                <th className="px-4 py-2.5 font-medium text-slate-500">Parent</th>
                <th className="px-4 py-2.5 font-medium text-slate-500">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredNodes.map((node) => (
                <tr key={node.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2.5">
                    {editingNode === node.id ? (
                      <div className="flex items-center gap-1">
                        <input
                          value={editLabel}
                          onChange={(e) => setEditLabel(e.target.value)}
                          onKeyDown={(e) => e.key === 'Enter' && handleRename(node.id)}
                          className="input-base w-40 text-xs"
                          autoFocus
                        />
                        <button onClick={() => handleRename(node.id)} className="text-xs text-primary-600">Save</button>
                        <button onClick={() => setEditingNode(null)} className="text-xs text-slate-400">Cancel</button>
                      </div>
                    ) : (
                      <span className="font-medium text-slate-800">{node.label}</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 tabular-nums text-slate-600">{node.unitCount}</td>
                  <td className="px-4 py-2.5 text-slate-500">
                    {node.parentId ? allNodes.find((n) => n.id === node.parentId)?.label ?? '—' : '(root)'}
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => { setEditingNode(node.id); setEditLabel(node.label) }}
                        className="text-xs text-primary-600 hover:underline"
                      >
                        Rename
                      </button>
                      {mergeTarget === node.id ? (
                        <div className="flex items-center gap-1">
                          <select
                            value={mergeInto}
                            onChange={(e) => setMergeInto(e.target.value)}
                            className="input-base w-36 text-xs"
                          >
                            <option value="">Merge into…</option>
                            {allNodes
                              .filter((n) => n.id !== node.id)
                              .map((n) => (
                                <option key={n.id} value={n.id}>{n.label}</option>
                              ))}
                          </select>
                          <button onClick={() => handleMerge(node.id)} className="text-xs text-primary-600">Go</button>
                          <button onClick={() => setMergeTarget(null)} className="text-xs text-slate-400">Cancel</button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setMergeTarget(node.id)}
                          className="text-xs text-slate-500 hover:underline"
                        >
                          Merge
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Thresholds */}
      <section className="mt-10">
        <h2 className="text-lg font-semibold text-slate-900">Thresholds</h2>
        <p className="mt-1 text-sm text-slate-500">Configure classification and deduplication sensitivity</p>

        <div className="mt-4 grid gap-6 sm:grid-cols-3">
          <div className="card p-4">
            <label className="label-base">Duplicate threshold</label>
            <input
              type="range"
              min={0.5}
              max={1}
              step={0.01}
              value={thresholds.duplicate}
              onChange={(e) => setThresholds((t) => ({ ...t, duplicate: parseFloat(e.target.value) }))}
              className="mt-2 w-full accent-primary-600"
            />
            <p className="mt-1 text-center text-sm font-medium tabular-nums text-slate-700">
              {(thresholds.duplicate * 100).toFixed(0)}%
            </p>
          </div>
          <div className="card p-4">
            <label className="label-base">Topic match threshold</label>
            <input
              type="range"
              min={0.5}
              max={1}
              step={0.01}
              value={thresholds.topicMatch}
              onChange={(e) => setThresholds((t) => ({ ...t, topicMatch: parseFloat(e.target.value) }))}
              className="mt-2 w-full accent-primary-600"
            />
            <p className="mt-1 text-center text-sm font-medium tabular-nums text-slate-700">
              {(thresholds.topicMatch * 100).toFixed(0)}%
            </p>
          </div>
          <div className="card p-4">
            <label className="label-base">New topic confidence floor</label>
            <input
              type="range"
              min={0.3}
              max={0.9}
              step={0.01}
              value={thresholds.newTopicFloor}
              onChange={(e) => setThresholds((t) => ({ ...t, newTopicFloor: parseFloat(e.target.value) }))}
              className="mt-2 w-full accent-primary-600"
            />
            <p className="mt-1 text-center text-sm font-medium tabular-nums text-slate-700">
              {(thresholds.newTopicFloor * 100).toFixed(0)}%
            </p>
          </div>
        </div>
      </section>

      {/* Alert Rules */}
      <section className="mt-10 pb-8">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Alert Rules</h2>
            <p className="mt-1 text-sm text-slate-500">Configure automated notifications for topic changes</p>
          </div>
          <button onClick={handleAddRule} className="btn-primary text-sm">+ Add rule</button>
        </div>

        <div className="mt-4 space-y-3">
          {alertRules.map((rule) => (
            <div key={rule.id} className="card flex items-center gap-4 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm text-slate-800">{rule.condition}</p>
                <p className="text-xs text-slate-500">→ {rule.channel}</p>
              </div>
              <button
                onClick={() => handleDeleteRule(rule.id)}
                className="shrink-0 text-xs text-red-500 hover:underline"
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
