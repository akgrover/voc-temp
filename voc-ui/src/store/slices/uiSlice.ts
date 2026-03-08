import { createSlice, type PayloadAction } from '@reduxjs/toolkit'
import type { RootState } from '../index'

export type DateRangePreset = '7d' | '30d' | '90d' | 'custom'

type UiState = {
  globalSearch: string
  dateRange: DateRangePreset
  notificationBellOpen: boolean
  selectedTopicId: string | null
  selectedAccountId: string | null
  activeModal: string | null
}

const initialState: UiState = {
  globalSearch: '',
  dateRange: '30d',
  notificationBellOpen: false,
  selectedTopicId: null,
  selectedAccountId: null,
  activeModal: null,
}

const uiSlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    setGlobalSearch(state, action: PayloadAction<string>) {
      state.globalSearch = action.payload
    },
    setDateRange(state, action: PayloadAction<DateRangePreset>) {
      state.dateRange = action.payload
    },
    toggleNotificationBell(state) {
      state.notificationBellOpen = !state.notificationBellOpen
    },
    closeNotificationBell(state) {
      state.notificationBellOpen = false
    },
    setSelectedTopicId(state, action: PayloadAction<string | null>) {
      state.selectedTopicId = action.payload
    },
    setSelectedAccountId(state, action: PayloadAction<string | null>) {
      state.selectedAccountId = action.payload
    },
    openModal(state, action: PayloadAction<string>) {
      state.activeModal = action.payload
    },
    closeModal(state) {
      state.activeModal = null
    },
  },
})

export const {
  setGlobalSearch,
  setDateRange,
  toggleNotificationBell,
  closeNotificationBell,
  setSelectedTopicId,
  setSelectedAccountId,
  openModal,
  closeModal,
} = uiSlice.actions

// --- Selectors ---

export const selectGlobalSearch = (state: RootState) => state.ui.globalSearch
export const selectDateRange = (state: RootState) => state.ui.dateRange
export const selectNotificationBellOpen = (state: RootState) => state.ui.notificationBellOpen
export const selectActiveModal = (state: RootState) => state.ui.activeModal

export default uiSlice.reducer
