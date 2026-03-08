import { useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { MOCK_FEEDBACK_UNITS } from '../../store/mockData/feedbackUnits'
import EmptyState from '../../components/EmptyState/EmptyState'

export default function ReviewQueue() {
  const [toast, setToast] = useState<string | null>(null)

  const reviewQueue = useMemo(
    () => MOCK_FEEDBACK_UNITS.filter((u) => u.confidence < 0.70).sort((a, b) => a.confidence - b.confidence),
    [],
  )

  const showToast = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(null), 2500)
  }

  const handleAcceptTopic = (unitId: string) => {
    showToast(`Accepted classification for unit ${unitId}`)
  }

  const handleReassign = (_unitId: string) => {
    showToast('Reassignment is not implemented in this mock')
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <Link to="/taxonomy" className="text-sm text-primary-600 hover:underline">← Back to Taxonomy</Link>

      <div className="mt-3">
        <h1 className="page-title">Review Queue</h1>
        <p className="page-description">
          Low-confidence feedback units that need manual review ({reviewQueue.length} items)
        </p>
      </div>

      {toast && (
        <div className="fixed bottom-6 right-6 z-50 animate-fade-in rounded-lg bg-slate-900 px-4 py-2.5 text-sm text-white shadow-lg">
          {toast}
        </div>
      )}

      {reviewQueue.length === 0 ? (
        <div className="mt-8">
          <EmptyState message="All feedback is classified. Nothing to review." />
        </div>
      ) : (
        <div className="mt-6 space-y-3">
          {reviewQueue.map((u) => (
            <div key={u.id} className="card px-4 py-3">
              <p className="text-sm text-slate-800">{u.text}</p>
              <div className="mt-2 flex flex-wrap items-center gap-3">
                <span className="rounded-md bg-primary-50 px-1.5 py-0.5 text-xs font-medium text-primary-700">
                  Suggested: {u.topicLabel}
                </span>
                <span className="text-xs text-slate-500">
                  Confidence: <strong className="text-orange-600">{(u.confidence * 100).toFixed(0)}%</strong>
                </span>
                <span className="text-xs text-slate-400">{u.accountName} · {u.date}</span>
              </div>
              <div className="mt-2 flex items-center gap-2">
                <button
                  onClick={() => handleAcceptTopic(u.id)}
                  className="rounded-md bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 hover:bg-emerald-100"
                >
                  Accept
                </button>
                <button
                  onClick={() => handleReassign(u.id)}
                  className="rounded-md bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-200"
                >
                  Reassign
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
