import { createSlice, type PayloadAction } from '@reduxjs/toolkit'
import { MOCK_TAXONOMY, type TaxonomyNode } from '../mockData/taxonomy'
import type { RootState } from '../index'

type TaxonomyState = {
  nodes: TaxonomyNode[]
}

const initialState: TaxonomyState = {
  nodes: MOCK_TAXONOMY,
}

const taxonomySlice = createSlice({
  name: 'taxonomy',
  initialState,
  reducers: {
    renameNode(state, action: PayloadAction<{ id: string; label: string }>) {
      const node = state.nodes.find((n) => n.id === action.payload.id)
      if (node) node.label = action.payload.label
    },
    mergeNodes(state, action: PayloadAction<{ sourceId: string; targetId: string }>) {
      const source = state.nodes.find((n) => n.id === action.payload.sourceId)
      const target = state.nodes.find((n) => n.id === action.payload.targetId)
      if (source && target) {
        target.unitCount += source.unitCount
        state.nodes = state.nodes.filter((n) => n.id !== action.payload.sourceId)
        state.nodes
          .filter((n) => n.parentId === action.payload.sourceId)
          .forEach((child) => {
            child.parentId = action.payload.targetId
          })
      }
    },
  },
})

export const { renameNode, mergeNodes } = taxonomySlice.actions

// --- Selectors ---

export const selectFlatNodes = (state: RootState): TaxonomyNode[] => state.taxonomy.nodes

export const selectNodeById = (state: RootState, id: string): TaxonomyNode | undefined =>
  state.taxonomy.nodes.find((n) => n.id === id)

export const selectChildren = (state: RootState, parentId: string): TaxonomyNode[] =>
  state.taxonomy.nodes.filter((n) => n.parentId === parentId)

export const selectRootNodes = (state: RootState): TaxonomyNode[] =>
  state.taxonomy.nodes.filter((n) => n.parentId === null)

export default taxonomySlice.reducer
