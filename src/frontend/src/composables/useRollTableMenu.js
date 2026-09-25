import { ref } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useEffectApplication } from '@/composables/useEffectApplication.js'

// Roll-table-as-menu (B58): open a roll table, list its entries as a pickable
// menu, then apply the chosen entry (pay cost effects, gain effects).
const EFFECT_FIELDS = `
  timing type action target entity result dieFilter negative
  context duration { timers { event remaining } combine } targetSpec entitySpec resultSpec ownerSpec refs
  conditions { type subject target targets value operator narrative spec }
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
            id name scheme die
            entries {
              label description weight minValue maxValue tier
              conditions { type subject target targets value operator narrative }
              costEffects { ${EFFECT_FIELDS} }
              effects { ${EFFECT_FIELDS} }
            }
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
            pendingChoices { index kind scope field effect { ${EFFECT_FIELDS} } }
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

  async function createSupport({ playerId, mainEntityId, tableId, index }) {
    loading.value = true
    try {
      const data = await graphql(
        `mutation($playerId: ID!, $mainEntityId: ID!, $tableId: ID!, $index: Int!) {
          createSupportCharacter(playerId: $playerId, mainEntityId: $mainEntityId, tableId: $tableId, index: $index) {
            id type name razmerit
          }
        }`,
        { playerId, mainEntityId, tableId, index },
      )
      return data?.createSupportCharacter || null
    } finally {
      loading.value = false
    }
  }

  return { loading, fetchTable, applyEntry, createSupport, resolveEffectTargets }
}
