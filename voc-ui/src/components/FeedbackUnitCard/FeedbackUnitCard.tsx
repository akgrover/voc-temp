import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAppDispatch } from '../../store/hooks'
import { toggleStarUnit } from '../../store/slices/feedbackSlice'
import type { FeedbackUnit } from '../../store/mockData/feedbackUnits'
import SentimentBadge from '../SentimentBadge/SentimentBadge'

const intentLabels: Record<string, { label: string; color: string }> = {
  bug_report: { label: 'Bug', color: 'bg-red-100 text-red-700' },
  feature_request: { label: 'Feature Request', color: 'bg-purple-100 text-purple-700' },
  praise: { label: 'Praise', color: 'bg-emerald-100 text-emerald-700' },
  churn_signal: { label: 'Churn Signal', color: 'bg-orange-100 text-orange-700' },
  question: { label: 'Question', color: 'bg-sky-100 text-sky-700' },
}

export default function FeedbackUnitCard({ unit }: { unit: FeedbackUnit }) {
  const dispatch = useAppDispatch()
  const [expanded, setExpanded] = useState(false)
  const intent = intentLabels[unit.intentType] ?? { label: unit.intentType, color: 'bg-slate-100 text-slate-700' }

  return (
    <div className="card transition-shadow hover:shadow-card-hover">
      <button
        type="button"
        className="w-full px-4 py-3 text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <p className={`text-sm text-slate-800 ${expanded ? '' : 'line-clamp-2'}`}>{unit.text}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Link
                to={`/taxonomy/${unit.topicId}`}
                onClick={(e) => e.stopPropagation()}
                className="rounded-md bg-primary-50 px-1.5 py-0.5 text-xs font-medium text-primary-700 hover:bg-primary-100"
              >
                {unit.topicLabel}
              </Link>
              <span className={`rounded-md px-1.5 py-0.5 text-xs font-medium ${intent.color}`}>
                {intent.label}
              </span>
              <SentimentBadge polarity={unit.sentiment.polarity} />
              <Link
                to={`/accounts/${unit.accountId}`}
                onClick={(e) => e.stopPropagation()}
                className="text-xs text-slate-500 hover:text-primary-600"
              >
                {unit.accountName}
              </Link>
              <span className="text-xs text-slate-400">{unit.date}</span>
            </div>
          </div>

          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); dispatch(toggleStarUnit(unit.id)) }}
            className="shrink-0 text-lg"
            aria-label={unit.isStarred ? 'Unstar' : 'Star'}
          >
            {unit.isStarred ? '★' : '☆'}
          </button>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-slate-100 bg-slate-50/50 px-4 py-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="text-xs font-medium text-slate-500">Source</p>
              <p className="text-sm text-slate-800">{unit.sourceChannel}</p>
              {unit.sourceUrl && (
                <a href={unit.sourceUrl} target="_blank" rel="noreferrer" className="text-xs text-primary-600 hover:underline">
                  View source
                </a>
              )}
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500">Confidence</p>
              <p className="text-sm text-slate-800">{(unit.confidence * 100).toFixed(0)}%</p>
            </div>
            {unit.duplicateCount && (
              <div>
                <p className="text-xs font-medium text-slate-500">Duplicates</p>
                <p className="text-sm text-slate-800">{unit.duplicateCount} similar reports</p>
              </div>
            )}
            <div>
              <p className="text-xs font-medium text-slate-500">Sentiment Details</p>
              <p className="text-sm text-slate-800 capitalize">
                {unit.sentiment.intensity} · {unit.sentiment.emotions.join(', ')}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
