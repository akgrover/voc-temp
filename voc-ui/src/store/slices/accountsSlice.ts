import { createSlice, type PayloadAction } from '@reduxjs/toolkit'
import { MOCK_ACCOUNTS, type Account } from '../mockData/accounts'
import type { RootState } from '../index'

export type AccountSortBy = 'most_units' | 'worst_sentiment' | 'most_recent' | 'alphabetical'

type AccountsState = {
  accounts: Account[]
}

const initialState: AccountsState = {
  accounts: MOCK_ACCOUNTS,
}

const accountsSlice = createSlice({
  name: 'accounts',
  initialState,
  reducers: {
    toggleStarAccount(state, action: PayloadAction<string>) {
      const account = state.accounts.find((a) => a.id === action.payload)
      if (account) account.isStarred = !account.isStarred
    },
  },
})

export const { toggleStarAccount } = accountsSlice.actions

// --- Selectors ---

export const selectSortedAccounts = (state: RootState, sortBy: AccountSortBy): Account[] => {
  const accounts = [...state.accounts.accounts]
  const sortFns: Record<AccountSortBy, (a: Account, b: Account) => number> = {
    most_units: (a, b) => b.unitCount - a.unitCount,
    worst_sentiment: (a, b) => a.netSentiment - b.netSentiment,
    most_recent: (a, b) => new Date(b.lastFeedbackDate).getTime() - new Date(a.lastFeedbackDate).getTime(),
    alphabetical: (a, b) => a.name.localeCompare(b.name),
  }
  accounts.sort(sortFns[sortBy])
  return accounts
}

export const selectAllAccounts = (state: RootState): Account[] => state.accounts.accounts

export const selectAccountById = (state: RootState, id: string): Account | undefined =>
  state.accounts.accounts.find((a) => a.id === id)

export default accountsSlice.reducer
