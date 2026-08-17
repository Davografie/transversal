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

  function substituteEffectDie(effects, effectDie) {
    const die = effectDie || 'd4'
    return (effects || []).map((e) => ({
      ...e,
      result: e.result != null ? e.result.replace('{effect_die}', die) : e.result,
    }))
  }

  async function applyOption(entityId, option, effectDie) {
    // Applies the option's effects with the roll's effect die substituted in.
    // Returns { applied, pendingChoices }.
    const effects = substituteEffectDie(option.effects || [], effectDie)
    return applyEffects(entityId, effects)
  }

  return { loading, fetchConsequenceOptions, applyOption, resolveEffectTargets }
}
