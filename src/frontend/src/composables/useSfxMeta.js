import { ref } from 'vue'
import { useApi } from './useApi.js'

// Trigger + condition-type vocabularies, sourced from the backend `triggers` and
// `conditionTypes` resolvers (single source of truth — no frontend hardcoding).
const META_QUERY = `{
  triggers { value label group requiresSourceElements }
  conditionTypes { value label group needsTarget targetPlaceholder targetKind valueKind operators targetOptions usesSpec requiresContextAnyOf requiresSourceElements }
  targetFilterFields { field label valueType kinds options }
}`

// What a condition can read at one evaluation point (null = not modelled, so
// nothing is forbidden). Asked per (trigger, placement, timing) rather than
// re-derived here, so the editor and `validate_sfx` share one map.
const CONTEXT_KEYS_QUERY = `query($trigger: String, $placement: String, $timing: String) {
  conditionContextKeys(trigger: $trigger, placement: $placement, timing: $timing)
}`

// Module-level cache so the SFX editor and condition editor share one fetch.
const triggers = ref([])
const conditionTypes = ref([])
const targetFilterFields = ref([])
const contextKeys = new Map()
let loaded = false
let pending = null

export function useSfxMeta() {
  const { graphql } = useApi()

  async function load() {
    if (loaded) return
    if (pending) return pending
    pending = graphql(META_QUERY)
      .then((data) => {
        triggers.value = data?.triggers || []
        conditionTypes.value = data?.conditionTypes || []
        targetFilterFields.value = data?.targetFilterFields || []
        loaded = true
      })
      .finally(() => { pending = null })
    return pending
  }

  async function contextKeysFor(trigger = '', placement = '', timing = '') {
    const key = `${trigger}|${placement}|${timing}`
    if (contextKeys.has(key)) return contextKeys.get(key)
    const data = await graphql(CONTEXT_KEYS_QUERY, {
      trigger: trigger || null, placement: placement || null, timing: timing || null,
    })
    const keys = data?.conditionContextKeys ?? null
    contextKeys.set(key, keys)
    return keys
  }

  return { load, triggers, conditionTypes, targetFilterFields, contextKeysFor }
}
