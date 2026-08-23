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
            effects { timing type action target entity result targetScope targetFilter negative context }
          }
        }`
      )
      return data?.hitchMenu || []
    } finally {
      loading.value = false
    }
  }

  function substituteVariables(effects, vars) {
    const values = Object.fromEntries(
      Object.entries(vars || {}).map(([k, v]) => [k, String(v ?? '')])
    )
    const sub = (s) =>
      typeof s === 'string'
        ? Object.entries(values).reduce((acc, [k, v]) => acc.replaceAll(`{${k}}`, v), s)
        : s

    return (effects || []).map((e) => {
      const out = { ...e }
      for (const field of ['result', 'target', 'entity', 'targetScope']) {
        if (out[field] != null) out[field] = sub(out[field])
      }
      if (out.context && typeof out.context === 'object') {
        out.context = Object.fromEntries(
          Object.entries(out.context).map(([k, v]) => [k, sub(v)])
        )
      }
      return out
    })
  }

  async function applyOption(entityId, option, vars) {
    const effects = substituteVariables(option.effects || [], vars)
    return applyEffects(entityId, effects)
  }

  return { loading, fetchHitchMenu, applyOption, resolveEffectTargets }
}
