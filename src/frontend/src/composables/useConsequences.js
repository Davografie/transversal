import { ref } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useEffectApplication } from '@/composables/useEffectApplication.js'

// Fetch + apply the post-roll consequence menu for an entity and side.
export function useConsequences() {
  const { graphql } = useApi()
  const { applyEffects, resolveEffectTargets } = useEffectApplication()
  const loading = ref(false)

  async function fetchConsequenceOptions(entityId, side) {
    loading.value = true
    try {
      const data = await graphql(
        `query($entityId: ID!, $side: String!) {
          consequenceOptions(entityId: $entityId, side: $side) {
            id label side source
            effects { timing type action target result targetScope context }
          }
        }`,
        { entityId, side }
      )
      return data?.consequenceOptions || []
    } finally {
      loading.value = false
    }
  }

  async function applyOption(entityId, option) {
    // Applies the option's effects; returns { applied, pendingChoices }.
    return applyEffects(entityId, option.effects || [])
  }

  return { loading, fetchConsequenceOptions, applyOption, resolveEffectTargets }
}
