import { createSlice, type PayloadAction } from '@reduxjs/toolkit'
import { MOCK_FEEDBACK_UNITS, type FeedbackUnit, type IntentType } from '../mockData/feedbackUnits'
import type { RootState } from '../index'

export type SortBy = 'most_recent' | 'oldest' | 'worst_sentiment' | 'best_sentiment' | 'most_accounts'

export type FeedbackFilters = {
  dateRange: { start: string; end: string } | null
  intentTypes: IntentType[]
  sentimentRange: { min: number; max: number } | null
  topicId: string | null
  accountId: string | null
  minAccounts: number
  starredOnly: boolean
  sortBy: SortBy
}

type FeedbackState = {
  units: FeedbackUnit[]
  filters: FeedbackFilters
}

const initialFilters: FeedbackFilters = {
  dateRange: null,
  intentTypes: [],
  sentimentRange: null,
  topicId: null,
  accountId: null,
  minAccounts: 1,
  starredOnly: false,
  sortBy: 'most_recent',
}

const initialState: FeedbackState = {
  units: MOCK_FEEDBACK_UNITS,
  filters: initialFilters,
}

const feedbackSlice = createSlice({
  name: 'feedback',
  initialState,
  reducers: {
    toggleStarUnit(state, action: PayloadAction<string>) {
      const unit = state.units.find((u) => u.id === action.payload)
      if (unit) unit.isStarred = !unit.isStarred
    },
    setFilters(state, action: PayloadAction<Partial<FeedbackFilters>>) {
      state.filters = { ...state.filters, ...action.payload }
    },
    resetFilters(state) {
      state.filters = initialFilters
    },
  },
})

export const { toggleStarUnit, setFilters, resetFilters } = feedbackSlice.actions

// --- Selectors ---

export const selectFilteredUnits = (state: RootState): FeedbackUnit[] => {
  const { units, filters } = state.feedback
  let result = [...units]

  if (filters.dateRange) {
    const { start, end } = filters.dateRange
    result = result.filter((u) => u.date >= start && u.date <= end)
  }
  if (filters.intentTypes.length > 0) {
    result = result.filter((u) => filters.intentTypes.includes(u.intentType))
  }
  if (filters.sentimentRange) {
    const { min, max } = filters.sentimentRange
    result = result.filter((u) => u.sentiment.polarity >= min && u.sentiment.polarity <= max)
  }
  if (filters.topicId) {
    result = result.filter((u) => u.topicId === filters.topicId)
  }
  if (filters.accountId) {
    result = result.filter((u) => u.accountId === filters.accountId)
  }
  if (filters.starredOnly) {
    result = result.filter((u) => u.isStarred)
  }

  const sortFns: Record<SortBy, (a: FeedbackUnit, b: FeedbackUnit) => number> = {
    most_recent: (a, b) => b.date.localeCompare(a.date),
    oldest: (a, b) => a.date.localeCompare(b.date),
    worst_sentiment: (a, b) => a.sentiment.polarity - b.sentiment.polarity,
    best_sentiment: (a, b) => b.sentiment.polarity - a.sentiment.polarity,
    most_accounts: (a, b) => (b.duplicateCount ?? 0) - (a.duplicateCount ?? 0),
  }
  result.sort(sortFns[filters.sortBy])

  return result
}

export const selectFeedbackFilters = (state: RootState) => state.feedback.filters

export default feedbackSlice.reducer
