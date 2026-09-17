import { computed, ref } from 'vue'
import { useApi } from './useApi.js'

// ── Module-level state, keyed per life path ──────────
// Keyed so two roll-table panels on different life paths cannot clobber each
// other's list (they used to share one `tables` ref and re-fetch on activation).
const tablesByPath = ref({})  // lifePathId ('' = unlinked) → list
const allTables = ref([])     // all tables ({ id name universe lifePath }) for grouping
const allTableNames = ref({}) // id → name, for human-friendly effect summaries
const loading = ref(false)

const ROLL_TABLE_FIELDS = `
  id name universe lifePath scheme rollSource traitDiceCount die
  check { traitIds difficulty freeChoice }
  entries {
    label description minValue maxValue weight tier
    conditions { type subject target targets value operator narrative spec }
    effects { timing type action target result negative context }
  }
`

export function useRollTables() {
  const { graphql } = useApi()

  async function fetchTables(lifePathId = null) {
    const key = lifePathId || ''
    loading.value = true
    const data = await graphql(
      `query($lp:String){ rollTables(lifePathId:$lp){ id name scheme rollSource die } }`,
      { lp: lifePathId },
    )
    tablesByPath.value = { ...tablesByPath.value, [key]: data?.rollTables || [] }
    loading.value = false
    return tablesByPath.value[key]
  }

  // A path's list — reactive to both the store and the key.
  function tablesFor(lifePathId = null) {
    return computed(() => tablesByPath.value[lifePathId || ''] || [])
  }

  // Apply an updater to every bucket (a table lives in exactly one, but which
  // one is not the caller's business).
  function _patchBuckets(updater) {
    const next = { ...tablesByPath.value }
    for (const key of Object.keys(next)) {
      const list = next[key] || []
      const out = updater(list)
      if (out !== list) next[key] = out
    }
    tablesByPath.value = next
  }

  function _putTable(t) {
    let placed = false
    _patchBuckets((list) => {
      const idx = list.findIndex(x => x.id === t.id)
      if (idx < 0) return list
      placed = true
      return list.map((x, i) => (i === idx ? t : x))
    })
    if (!placed) {
      const key = t.lifePath || ''
      tablesByPath.value = { ...tablesByPath.value, [key]: [...(tablesByPath.value[key] || []), t] }
    }
    allTableNames.value = { ...allTableNames.value, [t.id]: t.name }
  }

  async function fetchAllTableNames() {
    const data = await graphql(`{ rollTables { id name } }`)
    const map = {}
    for (const t of data?.rollTables || []) map[t.id] = t.name
    allTableNames.value = map
    return map
  }

  async function fetchAllTables() {
    const data = await graphql(`{ rollTables { id name universe lifePath } }`)
    allTables.value = data?.rollTables || []
    return allTables.value
  }

  async function fetchTable(id) {
    loading.value = true
    const data = await graphql(`query($id:ID!){ rollTable(id:$id){ ${ROLL_TABLE_FIELDS} } }`, { id })
    const t = data?.rollTable || null
    if (t) _putTable(t)
    loading.value = false
    return t
  }

  async function saveRollTable(input) {
    const data = await graphql(
      `mutation($input:RollTableInput!){ saveRollTable(input:$input){ ${ROLL_TABLE_FIELDS} } }`,
      { input },
    )
    const t = data?.saveRollTable || null
    if (t) _putTable(t)
    return t
  }

  async function deleteRollTable(id) {
    const data = await graphql(`mutation($id:ID!){ deleteRollTable(id:$id) }`, { id })
    if (data?.deleteRollTable) {
      _patchBuckets((list) => (list.some(t => t.id === id) ? list.filter(t => t.id !== id) : list))
    }
    return data?.deleteRollTable
  }

  return {
    tablesByPath, tablesFor, allTables, allTableNames, loading,
    fetchTables, fetchAllTables, fetchAllTableNames, fetchTable, saveRollTable, deleteRollTable,
  }
}
