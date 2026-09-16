import { ref } from 'vue'

// Module-level singleton so all consumers share one fetch + one name map.
const names = ref({})
// The same set as a chooser list — `[{ value: universeKey, label: name }]`, name
// order — so a universe *picker* (the projection panel's scope filter) need not
// re-derive keys from the flattened map.
const options = ref([])
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
      options.value = (json.data?.entities || [])
        .filter((u) => u.currentUniverse)
        .map((u) => ({ value: u.currentUniverse, label: u.name }))
        .sort((a, b) => String(a.label).localeCompare(String(b.label)))
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

  return { names, options, name, load }
}
