import { computed, ref } from 'vue'
import { useApi } from './useApi.js'

// ── Module-level state, keyed per universe ───────────
// Keyed so two panels showing different universes cannot clobber each other's
// list (they used to share one `paths` ref and re-fetch on activation).
const pathsByUniverse = ref({})
const loading = ref(false)

const LIFE_PATH_FIELDS = `
  id name universe description entryTableId
  factionIds
  discovery { atLocation knowsEntity possessesTrait hasTraitRating hasRelationship }
`

export function useLifePaths() {
  const { graphql } = useApi()

  async function fetchLifePaths(universe) {
    if (!universe) return []
    loading.value = true
    const data = await graphql(
      `query($u: String!) { lifePaths(universe: $u) { ${LIFE_PATH_FIELDS} } }`,
      { u: universe },
    )
    pathsByUniverse.value = { ...pathsByUniverse.value, [universe]: data?.lifePaths || [] }
    loading.value = false
    return pathsByUniverse.value[universe]
  }

  // A universe's list — reactive to both the store and the key, so two panels
  // on different universes each read their own.
  function pathsFor(universe) {
    return computed(() => pathsByUniverse.value[universe || ''] || [])
  }

  // Apply an updater to every bucket (a saved path lives in exactly one, but
  // which one is not the caller's business).
  function _patchBuckets(updater) {
    const next = { ...pathsByUniverse.value }
    for (const key of Object.keys(next)) {
      const list = next[key] || []
      const out = updater(list)
      if (out !== list) next[key] = out
    }
    pathsByUniverse.value = next
  }

  async function saveLifePath({ id, name, universe, description, entryTableId = '', discovery = null }) {
    const isNew = !id
    const data = await graphql(
      `mutation($id:String!,$name:String!,$universe:String!,$description:String!,$entryTableId:String!,$discovery:JSON){
        saveLifePath(id:$id,name:$name,universe:$universe,description:$description,entryTableId:$entryTableId,discovery:$discovery)
      }`,
      { id: id || '', name, universe, description, entryTableId: entryTableId || '', discovery },
    )
    const result = data?.saveLifePath
    if (result?.ok) {
      const full = { id: result.id, name, universe, description, entryTableId: entryTableId || '', discovery: discovery || null }
      let placed = false
      _patchBuckets((list) => {
        const idx = list.findIndex(p => p.id === result.id)
        if (idx < 0) return list
        placed = true
        return list.map((p, i) => (i === idx ? full : p))
      })
      if (!placed) {
        pathsByUniverse.value = { ...pathsByUniverse.value, [universe]: [...(pathsByUniverse.value[universe] || []), full] }
      }
    }
    return { ...(result || {}), isNew }
  }

  async function deleteLifePath(id) {
    const data = await graphql(`mutation($id:ID!){ deleteLifePath(id:$id) }`, { id })
    if (data?.deleteLifePath) {
      _patchBuckets((list) => (list.some(p => p.id === id) ? list.filter(p => p.id !== id) : list))
    }
    return data?.deleteLifePath
  }

  return { pathsByUniverse, pathsFor, loading, fetchLifePaths, saveLifePath, deleteLifePath }
}
