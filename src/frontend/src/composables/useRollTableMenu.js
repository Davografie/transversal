import { ref } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useEffectApplication } from '@/composables/useEffectApplication.js'

// Roll-table-as-menu (B58): open a roll table, list its entries as a pickable
// menu, then apply the chosen entry (pay cost effects, gain effects).
const EFFECT_FIELDS = `
  timing type action target entity result targetScope entityScope targetFilter dieFilter negative
  context duration { timers { event remaining } combine } targetSpec entitySpec refs
  conditions { type subject target value operator narrative spec }
`

export function useRollTableMenu() {
  const { graphql } = useApi()
  const { resolveEffectTargets } = useEffectApplication()
  const loading = ref(false)

  async function fetchTable(tableId) {
    loading.value = true
    try {
      const data = await graphql(
        `query($id: ID!) {
          rollTable(id: $id) {
            id name
            entries { label description costEffects { ${EFFECT_FIELDS} } effects { ${EFFECT_FIELDS} } }
          }
        }`,
        { id: tableId },
      )
      return data?.rollTable || null
    } finally {
      loading.value = false
    }
  }

  async function applyEntry(entityId, tableId, index) {
    loading.value = true
    try {
      const data = await graphql(
        `mutation($entityId: ID!, $tableId: ID!, $index: Int!) {
          applyRollTableEntry(entityId: $entityId, tableId: $tableId, index: $index) {
            applied
            pendingChoices { index kind scope field filter effect { ${EFFECT_FIELDS} } }
            structured
          }
        }`,
        { entityId, tableId, index },
      )
      return data?.applyRollTableEntry || { applied: [], pendingChoices: [], structured: [] }
    } finally {
      loading.value = false
    }
  }

  return { loading, fetchTable, applyEntry, resolveEffectTargets }
}
