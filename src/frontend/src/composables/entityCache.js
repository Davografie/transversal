import { reactive } from 'vue'

// Module-level cache shared app-wide (no Pinia — matches the repo's
// dependency-free state style). TTLs bound how long a snapshot is trusted
// before a re-fetch; SSE-driven invalidation keeps it fresh without polling.
const SHEET_TTL_MS = 60_000
const ENTITY_TTL_MS = 60_000

const state = reactive({
  sheets: {},   // entityId -> { payload, at }
  entities: {}, // entityId -> { data, at }
})

function _fresh(entry, ttl) {
  return !!(entry && Date.now() - entry.at < ttl)
}

export function useEntityCache() {
  return {
    state,

    getSheet(id) {
      const e = state.sheets[id]
      return _fresh(e, SHEET_TTL_MS) ? e.payload : null
    },
    setSheet(id, payload) {
      if (!id) return
      state.sheets[id] = { payload, at: Date.now() }
    },
    invalidateSheet(id) {
      if (id) delete state.sheets[id]
    },

    getEntity(id) {
      const e = state.entities[id]
      return _fresh(e, ENTITY_TTL_MS) ? e.data : null
    },
    setEntity(id, data) {
      if (!id) return
      state.entities[id] = { data, at: Date.now() }
    },
    invalidateEntity(id) {
      if (id) delete state.entities[id]
    },

    invalidateAll() {
      for (const k of Object.keys(state.sheets)) delete state.sheets[k]
      for (const k of Object.keys(state.entities)) delete state.entities[k]
    },
  }
}
