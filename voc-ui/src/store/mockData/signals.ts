export type SignalSeverity = 'red' | 'yellow' | 'green'

export type Signal = {
  id: string
  message: string
  severity: SignalSeverity
  topicId: string
  accountCount: number
  date: string
}

export const MOCK_SIGNALS: Signal[] = [
  {
    id: 'sig-1',
    message: '"Login Failures" up 2.4× this week',
    severity: 'red',
    topicId: 'tax-login-fail',
    accountCount: 41,
    date: '2026-02-25',
  },
  {
    id: 'sig-2',
    message: '"Pricing Concerns" new cluster forming',
    severity: 'yellow',
    topicId: 'tax-pricing',
    accountCount: 12,
    date: '2026-02-24',
  },
  {
    id: 'sig-3',
    message: '"Onboarding Flow" sentiment improved significantly',
    severity: 'green',
    topicId: 'tax-onboarding',
    accountCount: 28,
    date: '2026-02-23',
  },
  {
    id: 'sig-4',
    message: '"Report Export" volume spiking — 34% above average',
    severity: 'red',
    topicId: 'tax-report-export',
    accountCount: 35,
    date: '2026-02-25',
  },
  {
    id: 'sig-5',
    message: '"Support Response" improving — 3 consecutive weeks of faster resolution',
    severity: 'green',
    topicId: 'tax-support-resp',
    accountCount: 19,
    date: '2026-02-22',
  },
]
