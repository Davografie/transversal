import { computed, ref } from 'vue'
import { useApi } from './useApi.js'

// ── Module-level state, keyed per universe ───────────
// Keyed so two panels showing different universes cannot clobber each other's
// list (they used to share one `paths` ref and re-fetch on activation).
const pathsByUniverse = ref({})
const loading = ref(false)

// The full effect shape EffectForm round-trips — the same selection the SFX
// editor uses (useSfxEdit.js), because a binding's `effects` are ordinary
// effects and a partial selection would drop what the editor wrote back.
const BINDING_EFFECT_FIELDS = `
  timing type action target entity result dieFilter negative context
  duration { timers { event remaining } combine }
  targetSpec entitySpec resultSpec ownerSpec refs output
  conditions { type subject target targets value operator narrative spec }
`

// ── The wrapper model ────────────────────────────────
// A path declares the tables it wraps (`steps`) and what each row of those
// tables means to *it* (`bindings`). A step's `id` is its own identity, not the
// table's; a binding's `key` names a row of the step's table (`RollTableEntry.key`).
const LIFE_PATH_FIELDS = `
  id name universe description entryTableId
  entryStep
  factionIds
  steps {
    id tableId label next
    bindings {
      key next exitKind exitPath enroll
      effects { ${BINDING_EFFECT_FIELDS} }
    }
  }
  conditions { type subject target targets value operator narrative spec }
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

  // Find a path wherever it is cached, so a leave-alone save can keep the
  // fields it is deliberately not sending (the wrapper, above all).
  function _findPath(id) {
    for (const list of Object.values(pathsByUniverse.value)) {
      const found = (list || []).find(p => p.id === id)
      if (found) return found
    }
    return null
  }

  // `steps` / `entryStep` are **optional and null means "leave the stored value
  // alone"**: a caller that omits them (an MCP script, a migration, a rename-only
  // edit) must not unwrap the path. So they are only put on the wire when this
  // caller actually supplies them — `undefined` omits, a list/string replaces.
  // The editor panel always supplies both; nothing else has to.
  async function saveLifePath({ id, name, universe, description, entryTableId = '', discovery = null, conditions = [], entryStep, steps }) {
    const isNew = !id
    const decls = ['$id:String!', '$name:String!', '$universe:String!', '$description:String!', '$entryTableId:String!', '$discovery:JSON', '$conditions:[ConditionInput!]']
    const args = ['id:$id', 'name:$name', 'universe:$universe', 'description:$description', 'entryTableId:$entryTableId', 'discovery:$discovery', 'conditions:$conditions']
    const vars = { id: id || '', name, universe, description, entryTableId: entryTableId || '', discovery, conditions: conditions || [] }
    if (steps !== undefined) {
      decls.push('$steps:[LifePathStepInput!]')
      args.push('steps:$steps')
      vars.steps = steps
    }
    if (entryStep !== undefined) {
      decls.push('$entryStep:String')
      args.push('entryStep:$entryStep')
      vars.entryStep = entryStep
    }
    const data = await graphql(
      `mutation(${decls.join(',')}){ saveLifePath(${args.join(',')}) }`,
      vars,
    )
    const result = data?.saveLifePath
    if (result?.ok) {
      // Keep whatever the server was told to leave alone: spread the cached copy
      // first, then override only the fields this save actually sent.
      const prev = _findPath(result.id) || {}
      const full = {
        ...prev,
        id: result.id, name, universe, description,
        entryTableId: entryTableId || '',
        discovery: discovery || null,
        conditions: conditions || [],
      }
      if (steps !== undefined) full.steps = steps
      if (entryStep !== undefined) full.entryStep = entryStep
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
