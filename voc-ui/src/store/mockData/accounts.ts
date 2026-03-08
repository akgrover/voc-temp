export type Account = {
  id: string
  name: string
  unitCount: number
  netSentiment: number
  topTopic: string
  lastFeedbackDate: string
  segment?: string
  isStarred: boolean
}

export const MOCK_ACCOUNTS: Account[] = [
  {
    id: 'acct-1',
    name: 'Acme Corp',
    unitCount: 87,
    netSentiment: -0.3,
    topTopic: 'Report Export',
    lastFeedbackDate: '2026-02-25T14:32:00Z',
    segment: 'Enterprise',
    isStarred: true,
  },
  {
    id: 'acct-2',
    name: 'Globex Industries',
    unitCount: 34,
    netSentiment: -0.7,
    topTopic: 'Login Failures',
    lastFeedbackDate: '2026-02-25T10:15:00Z',
    segment: 'Enterprise',
    isStarred: true,
  },
  {
    id: 'acct-3',
    name: 'Initech LLC',
    unitCount: 21,
    netSentiment: 0.4,
    topTopic: 'API Documentation',
    lastFeedbackDate: '2026-02-24T09:00:00Z',
    segment: 'Mid-Market',
    isStarred: false,
  },
  {
    id: 'acct-4',
    name: 'Umbrella Co',
    unitCount: 15,
    netSentiment: -0.8,
    topTopic: 'Pricing Concerns',
    lastFeedbackDate: '2026-02-22T16:45:00Z',
    segment: 'Mid-Market',
    isStarred: false,
  },
  {
    id: 'acct-5',
    name: 'TechStart Inc',
    unitCount: 42,
    netSentiment: 0.1,
    topTopic: 'Onboarding Flow',
    lastFeedbackDate: '2026-02-25T08:20:00Z',
    segment: 'Startup',
    isStarred: false,
  },
  {
    id: 'acct-6',
    name: 'Beta Labs',
    unitCount: 28,
    netSentiment: 0.5,
    topTopic: 'Search Speed',
    lastFeedbackDate: '2026-02-23T11:30:00Z',
    segment: 'Startup',
    isStarred: false,
  },
]
