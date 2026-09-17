import { ref } from 'vue'
import { useApi } from '@/composables/useApi.js'

// Drives the two-step effect application flow:
//   1. applyEffects  -> may return pendingChoices ({ index, kind, scope, effect })
//   2. resolveEffectTargets -> re-apply each pending effect with a chosen target
export function useEffectApplication() {
  const { graphql } = useApi()
  const applying = ref(false)

  async function applyEffects(entityId, effects) {
    applying.value = true
    try {
      const data = await graphql(
        `mutation($entityId: ID!, $effects: [EffectInput!]!) {
          applyEffects(entityId: $entityId, effects: $effects) {
            applied pendingChoices { index kind scope field effect { timing type action target entity result dieFilter negative context duration { timers { event remaining } combine } targetSpec entitySpec refs conditions { type subject target targets value operator narrative spec } } } structured
          }
        }`,
        { entityId, effects }
      )
      return data?.applyEffects || { applied: [], pendingChoices: [] }
    } finally {
      applying.value = false
    }
  }

  async function resolveEffectTargets(entityId, resolutions) {
    applying.value = true
    try {
      const data = await graphql(
        `mutation($entityId: ID!, $resolutions: [EffectTargetResolutionInput!]!) {
          resolveEffectTargets(entityId: $entityId, resolutions: $resolutions) {
            applied pendingChoices { index kind scope field effect { timing type action target entity result dieFilter negative context duration { timers { event remaining } combine } targetSpec entitySpec refs conditions { type subject target targets value operator narrative spec } } } structured
          }
        }`,
        { entityId, resolutions }
      )
      return data?.resolveEffectTargets || { applied: [], pendingChoices: [], structured: [] }
    } finally {
      applying.value = false
    }
  }

  return { applying, applyEffects, resolveEffectTargets }
}
