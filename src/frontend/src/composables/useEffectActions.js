import { ref } from 'vue'
import { useApi } from '@/composables/useApi.js'

const EFFECT_ACTIONS_QUERY = `{ effectActions { actionId label description category group effectType effectAction validTimings fields { name label fieldType required default options optionLabels hiddenWhenRef description } contextFields { name label fieldType required default options optionLabels hiddenWhenRef description } implicitTarget implicitResult implicitTiming targetKind pathElements durationElements requiresChoice supportsDuration supportsPolarity supportsReturnExit refs { name label element } refsFirst outputElement } }`

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
  // `resolve` (optional) maps a raw target id to a display name.
  function summarize(effect, resolve) {
    if (!effect) return ''
    let out = labelFor(effect)
    const target = resolve ? resolve(effect.target) : effect.target
    if (target && target !== 'self' && target !== '{source_trait}') out += ` → ${target}`
    if (effect.result) out += ` (${effect.result})`
    return out
  }

  return { load, labelFor, summarize, actions: cache }
}
