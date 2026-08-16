import { ref } from 'vue'
import { useApi } from './useApi.js'

// ── Module-level singleton state ─────────────────────
// All life-path panels share the same list; mutations update it in place.
const paths = ref([])
const loading = ref(false)

const LIFE_PATH_FIELDS = `
  id name universe description entryTableId
  factionIds
  discovery { atLocation knowsEntity possessesTrait hasTraitRating hasRelationship }
`

export function useLifePaths() {
  const { graphql } = useApi()

  async function fetchLifePaths(universe) {
    if (!universe) return paths.value
    loading.value = true
    const data = await graphql(
      `query($u: String!) { lifePaths(universe: $u) { ${LIFE_PATH_FIELDS} } }`,
      { u: universe },
    )
    paths.value = data?.lifePaths || []
    loading.value = false
    return paths.value
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
      const idx = paths.value.findIndex(p => p.id === result.id)
      if (idx >= 0) paths.value[idx] = full
      else paths.value.push(full)
    }
    return { ...(result || {}), isNew }
  }

  async function deleteLifePath(id) {
    const data = await graphql(`mutation($id:ID!){ deleteLifePath(id:$id) }`, { id })
    if (data?.deleteLifePath) {
      paths.value = paths.value.filter(p => p.id !== id)
    }
    return data?.deleteLifePath
  }

  return { paths, loading, fetchLifePaths, saveLifePath, deleteLifePath }
}
