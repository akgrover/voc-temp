type Props = {
  trend: string
  size?: 'sm' | 'md'
}

export default function TrendIndicator({ trend, size = 'sm' }: Props) {
  if (!trend || trend === '0%') {
    return <span className={`text-slate-400 ${size === 'sm' ? 'text-xs' : 'text-sm'}`}>—</span>
  }

  const isPositive = trend.startsWith('+')
  const color = isPositive ? 'text-emerald-600' : 'text-red-600'
  const arrow = isPositive ? '↑' : '↓'
  const textSize = size === 'sm' ? 'text-xs' : 'text-sm'

  return (
    <span className={`inline-flex items-center gap-0.5 font-medium ${color} ${textSize}`}>
      {arrow} {trend}
    </span>
  )
}
