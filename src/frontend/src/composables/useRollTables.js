import { ref } from 'vue'
import { useApi } from './useApi.js'

// ── Module-level singleton state ─────────────────────
const tables = ref([])        // lightweight list ({ id name scheme die }) for a path
const allTables = ref([])     // all tables ({ id name universe lifePath }) for grouping
const allTableNames = ref({}) // id → name, for human-friendly effect summaries
const loading = ref(false)

const ROLL_TABLE_FIELDS = `
  id name universe lifePath scheme rollSource traitDiceCount die
  check { traitIds difficulty freeChoice }
  entries {
    label description minValue maxValue weight tier
    conditions { type subject target value operator narrative spec }
    effects { timing type action target result targetScope negative context }
  }
`

export function useRollTables() {
  const { graphql } = useApi()

  async function fetchTables(lifePathId = null) {
    loading.value = true
    const data = await graphql(
      `query($lp:String){ rollTables(lifePathId:$lp){ id name scheme rollSource die } }`,
      { lp: lifePathId },
    )
    tables.value = data?.rollTables || []
    loading.value = false
    return tables.value
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
    if (t) {
      const idx = tables.value.findIndex(x => x.id === t.id)
      if (idx >= 0) tables.value[idx] = t
      allTableNames.value = { ...allTableNames.value, [t.id]: t.name }
    }
    loading.value = false
    return t
  }

  async function saveRollTable(input) {
    const data = await graphql(
      `mutation($input:RollTableInput!){ saveRollTable(input:$input){ ${ROLL_TABLE_FIELDS} } }`,
      { input },
    )
    const t = data?.saveRollTable || null
    if (t) {
      const idx = tables.value.findIndex(x => x.id === t.id)
      if (idx >= 0) tables.value[idx] = t
      else tables.value.push(t)
      allTableNames.value = { ...allTableNames.value, [t.id]: t.name }
    }
    return t
  }

  async function deleteRollTable(id) {
    const data = await graphql(`mutation($id:ID!){ deleteRollTable(id:$id) }`, { id })
    if (data?.deleteRollTable) {
      tables.value = tables.value.filter(t => t.id !== id)
    }
    return data?.deleteRollTable
  }

  return {
    tables, allTables, allTableNames, loading,
    fetchTables, fetchAllTables, fetchAllTableNames, fetchTable, saveRollTable, deleteRollTable,
  }
}
