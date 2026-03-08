import { createSlice, type PayloadAction } from '@reduxjs/toolkit'
import type { RootState } from '../index'

export type Collection = {
  id: string
  name: string
  unitIds: string[]
}

type StarredState = {
  collections: Collection[]
}

const initialState: StarredState = {
  collections: [
    { id: 'col-1', name: 'Q1 Review', unitIds: ['fu-1', 'fu-6'] },
    { id: 'col-2', name: 'Churn Risk', unitIds: ['fu-9', 'fu-37'] },
    { id: 'col-3', name: 'Share with PM', unitIds: ['fu-12'] },
  ],
}

const starredSlice = createSlice({
  name: 'starred',
  initialState,
  reducers: {
    createCollection(state, action: PayloadAction<string>) {
      state.collections.push({
        id: `col-${Date.now()}`,
        name: action.payload,
        unitIds: [],
      })
    },
    addToCollection(state, action: PayloadAction<{ collectionId: string; unitId: string }>) {
      const collection = state.collections.find((c) => c.id === action.payload.collectionId)
      if (collection && !collection.unitIds.includes(action.payload.unitId)) {
        collection.unitIds.push(action.payload.unitId)
      }
    },
    removeFromCollection(state, action: PayloadAction<{ collectionId: string; unitId: string }>) {
      const collection = state.collections.find((c) => c.id === action.payload.collectionId)
      if (collection) {
        collection.unitIds = collection.unitIds.filter((id) => id !== action.payload.unitId)
      }
    },
  },
})

export const { createCollection, addToCollection, removeFromCollection } = starredSlice.actions

// --- Selectors ---

export const selectAllCollections = (state: RootState): Collection[] => state.starred.collections

export const selectCollectionById = (state: RootState, id: string): Collection | undefined =>
  state.starred.collections.find((c) => c.id === id)

export default starredSlice.reducer
