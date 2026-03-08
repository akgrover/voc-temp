const polarityConfig = (polarity: number) => {
  if (polarity >= 0.5) return { emoji: '😊', label: 'Positive', color: 'bg-emerald-50 text-emerald-700 border-emerald-200' }
  if (polarity >= 0.1) return { emoji: '🙂', label: 'Slightly positive', color: 'bg-emerald-50/60 text-emerald-600 border-emerald-100' }
  if (polarity >= -0.1) return { emoji: '😐', label: 'Neutral', color: 'bg-slate-50 text-slate-600 border-slate-200' }
  if (polarity >= -0.5) return { emoji: '😕', label: 'Slightly negative', color: 'bg-amber-50 text-amber-700 border-amber-200' }
  return { emoji: '😠', label: 'Negative', color: 'bg-red-50 text-red-700 border-red-200' }
}

type Props = {
  polarity: number
  showScore?: boolean
  size?: 'sm' | 'md'
}

export default function SentimentBadge({ polarity, showScore = true, size = 'sm' }: Props) {
  const { emoji, color } = polarityConfig(polarity)
  const sizeClass = size === 'sm' ? 'px-1.5 py-0.5 text-xs' : 'px-2 py-1 text-sm'

  return (
    <span className={`inline-flex items-center gap-1 rounded-full border font-medium ${color} ${sizeClass}`}>
      <span>{emoji}</span>
      {showScore && <span>{polarity > 0 ? '+' : ''}{polarity.toFixed(2)}</span>}
    </span>
  )
}

export function SentimentBar({ polarity }: { polarity: number }) {
  const pct = ((polarity + 1) / 2) * 100
  const barColor = polarity >= 0.1 ? 'bg-emerald-500' : polarity <= -0.1 ? 'bg-red-500' : 'bg-amber-400'

  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 rounded-full bg-slate-100">
        <div className={`h-1.5 rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular-nums text-slate-500">{polarity > 0 ? '+' : ''}{polarity.toFixed(1)}</span>
    </div>
  )
}
