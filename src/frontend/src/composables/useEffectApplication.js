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
            applied pendingChoices { index kind scope field effect { timing type action target entity result dieFilter negative context duration { timers { event remaining } combine } targetSpec entitySpec resultSpec ownerSpec refs conditions { type subject target targets value operator narrative spec } } } structured
          }
        }`,
        { entityId, effects }
      )
      return data?.applyEffects || { applied: [], pendingChoices: [] }
    } finally {
      applying.value = false
    }
  }

  // `origin` says which host is answering, and the server echoes it on any *next*
  // question so the follow-up renders where this one is. Without it a sheet-triggered
  // follow-up would arrive tagged `roll` and open a second copy in the roller.
  async function resolveEffectTargets(entityId, resolutions, origin = null) {
    applying.value = true
    try {
      const data = await graphql(
        `mutation($entityId: ID!, $resolutions: [EffectTargetResolutionInput!]!, $origin: String) {
          resolveEffectTargets(entityId: $entityId, resolutions: $resolutions, origin: $origin) {
            applied pendingChoices { index kind scope field effect { timing type action target entity result dieFilter negative context duration { timers { event remaining } combine } targetSpec entitySpec resultSpec ownerSpec refs conditions { type subject target targets value operator narrative spec } } } structured
          }
        }`,
        { entityId, resolutions, origin }
      )
      return data?.resolveEffectTargets || { applied: [], pendingChoices: [], structured: [] }
    } finally {
      applying.value = false
    }
  }

  // Answer a loop prompt: run one more round of a rule whose own effect caused
  // the change it was handling. `structured` comes back carrying whatever the
  // round produced — including the *next* prompt, if it recursed again.
  async function resolveSfxLoop(choice, origin = null) {
    applying.value = true
    try {
      const data = await graphql(
        `mutation($entityId: ID!, $sfxId: ID!, $eventType: String!, $universe: String, $context: JSON, $origin: String) {
          resolveSfxLoop(entityId: $entityId, sfxId: $sfxId, eventType: $eventType, universe: $universe, context: $context, origin: $origin) {
            applied structured
          }
        }`,
        {
          entityId: choice.entity_id,
          sfxId: choice.sfx_id,
          eventType: choice.event_type,
          universe: choice.universe || '',
          context: choice.context || {},
          origin,
        }
      )
      return data?.resolveSfxLoop || { applied: [], structured: [] }
    } finally {
      applying.value = false
    }
  }

  return { applying, applyEffects, resolveEffectTargets, resolveSfxLoop }
}
