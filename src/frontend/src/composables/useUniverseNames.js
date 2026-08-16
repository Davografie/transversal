import { ref } from 'vue'

// Module-level singleton so all consumers share one fetch + one name map.
const names = ref({})
let loading = false
let loaded = false

export function useUniverseNames() {
  async function load() {
    if (loaded || loading) return
    loading = true
    try {
      const r = await fetch('/api/v1/graphql', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: '{ entities(type: UNIVERSE) { id name currentUniverse } }' }),
      })
      const json = await r.json()
      const map = {}
      for (const u of json.data?.entities || []) {
        if (u.currentUniverse) map[u.currentUniverse] = u.name
        if (u.id) map[u.id] = u.name
      }
      names.value = map
      loaded = true
    } catch {
      loaded = false
    } finally {
      loading = false
    }
  }

  function name(key) {
    return names.value[key] || key
  }

  return { names, name, load }
}
