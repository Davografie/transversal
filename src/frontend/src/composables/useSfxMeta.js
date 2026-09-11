import { ref } from 'vue'
import { useApi } from './useApi.js'

// Trigger + condition-type vocabularies, sourced from the backend `triggers` and
// `conditionTypes` resolvers (single source of truth — no frontend hardcoding).
const META_QUERY = `{
  triggers { value label group carriesContext }
  conditionTypes { value label needsTarget targetPlaceholder targetKind valueKind operators targetOptions usesSpec needsContext requiresSourceElements }
  targetFilterFields { field label valueType kinds options }
}`

// Module-level cache so the SFX editor and condition editor share one fetch.
const triggers = ref([])
const conditionTypes = ref([])
const targetFilterFields = ref([])
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

  return { load, triggers, conditionTypes, targetFilterFields }
}
