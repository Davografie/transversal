import { ref } from 'vue'
import { useApi } from '@/composables/useApi.js'

const EFFECT_ACTIONS_QUERY = `{ effectActions { actionId label description category effectType effectAction validTimings fields { name label fieldType required default options } implicitTarget implicitResult implicitTiming targetKind requiresChoice } }`

// Module-level cache so multiple panels share one fetch.
const cache = ref([])
let pending = null

export function useEffectActions() {
  const { graphql } = useApi()

  async function load() {
    if (cache.value.length) return cache.value
    if (pending) return pending
    pending = graphql(EFFECT_ACTIONS_QUERY)
      .then((data) => {
        cache.value = data?.effectActions || []
        return cache.value
      })
      .finally(() => { pending = null })
    return pending
  }

  function labelFor(effect) {
    if (!effect) return ''
    const meta = cache.value.find(a => a.effectType === effect.type && a.effectAction === effect.action)
    return meta?.label || (effect.type && effect.action ? `${effect.type}/${effect.action}` : '')
  }

  // Human-friendly one-line summary: "Step Up Die → highest trait die (d8)".
  function summarize(effect) {
    if (!effect) return ''
    let out = labelFor(effect)
    if (effect.target && effect.target !== 'self' && effect.target !== '{source_trait}') out += ` → ${effect.target}`
    if (effect.result) out += ` (${effect.result})`
    return out
  }

  return { load, labelFor, summarize, actions: cache }
}
