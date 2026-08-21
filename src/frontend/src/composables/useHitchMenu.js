import { ref } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useEffectApplication } from '@/composables/useEffectApplication.js'

// Fetch + apply the GM hitch menu (SFX whose menu_context is 'hitch').
export function useHitchMenu() {
  const { graphql } = useApi()
  const { applyEffects, resolveEffectTargets } = useEffectApplication()
  const loading = ref(false)

  async function fetchHitchMenu() {
    loading.value = true
    try {
      const data = await graphql(
        `query {
          hitchMenu {
            id label side source
            effects { timing type action target result targetScope negative context }
          }
        }`
      )
      return data?.hitchMenu || []
    } finally {
      loading.value = false
    }
  }

  function substituteCount(effects, count) {
    const n = String(count ?? 0)
    return (effects || []).map((e) => {
      const out = { ...e }
      if (out.result != null) out.result = out.result.replace('{number_of_hitches}', n)
      if (out.context && typeof out.context === 'object') {
        out.context = Object.fromEntries(
          Object.entries(out.context).map(([k, v]) => [
            k,
            typeof v === 'string' ? v.replace('{number_of_hitches}', n) : v,
          ])
        )
      }
      return out
    })
  }

  async function applyOption(entityId, option, count) {
    const effects = substituteCount(option.effects || [], count)
    return applyEffects(entityId, effects)
  }

  return { loading, fetchHitchMenu, applyOption, resolveEffectTargets }
}
