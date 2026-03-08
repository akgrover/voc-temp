import { configureStore } from '@reduxjs/toolkit'
import feedbackReducer from './slices/feedbackSlice'
import taxonomyReducer from './slices/taxonomySlice'
import accountsReducer from './slices/accountsSlice'
import starredReducer from './slices/starredSlice'
import uiReducer from './slices/uiSlice'

export const store = configureStore({
  reducer: {
    feedback: feedbackReducer,
    taxonomy: taxonomyReducer,
    accounts: accountsReducer,
    starred: starredReducer,
    ui: uiReducer,
  },
})

export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch
