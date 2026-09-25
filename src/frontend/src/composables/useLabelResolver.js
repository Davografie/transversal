import { ref } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useEffectActions } from '@/composables/useEffectActions.js'
import { useUniverseNames } from '@/composables/useUniverseNames.js'
import { useEntityCache } from '@/composables/entityCache.js'
import { conditionSummary, costSummary, effectSummary, entryKey } from '@/utils/rowSummary.js'

// One id → label resolver for every row surface. Supplied once, app-wide.
//
// This exists because the alternative was a live defect: each runtime surface
// resolved names from its own map, and the failures were silent —
// `LifePathWizard` read traits from `traitsByUniverse(<the path's universe>)`,
// so in a `three_realms` path `trait-rel-tenure` (stamped `universes: ["earth"]`)
// rendered as a raw id, on the two traits the life-path ladder is built from;
// the canvas `RollTableNode` resolved roll-table names only, so every trait
// target there rendered raw. Both had *correct* code for their own map.
//
// The map here is deliberately **registry-wide and universe-independent**: all
// 802 traits (read via every traitset, so one universe's stamping cannot hide a
// trait), all roll tables, all trait sets, every universe key. A row therefore
// resolves the same way wherever it is rendered, and a host carrying its own
// name map is a bug rather than a style choice. See [[UI-UX Design#Choice table]].
//
// Ids that are genuinely not registry members (a relationship target, a
// `{variable}` token) are returned unchanged — that is the honest answer, and
// the surface renders them in the dim "unresolved" tone so they read as ids
// rather than as names.

const names = ref({})
let pending = null
let loaded = false

const ROLL_TABLES = `{ rollTables { id name } }`
const TRAITSETS = `{ traitsets { id name } }`
const TRAITS_BY_TRAITSETS = `
  query($ids: [ID!]!) { traitsByTraitsets(traitsetIds: $ids) { id name } }
`

export function useLabelResolver() {
  const { graphql } = useApi()
  const { labelFor, load: loadActions } = useEffectActions()
  const universes = useUniverseNames()
  const cache = useEntityCache()

  /** Fetch the registry-wide map once per page; every consumer shares it. */
  async function load() {
    if (loaded) return names.value
    if (pending) return pending
    pending = (async () => {
      const map = {}
      // Traits: read by *traitset*, not by universe, so a trait one universe
      // stamps is still named in another. 36 sets → 802 traits, verified live.
      const [tables, sets] = await Promise.all([
        graphql(ROLL_TABLES).catch(() => null),
        graphql(TRAITSETS).catch(() => null),
      ])
      for (const t of tables?.rollTables || []) map[t.id] = t.name
      for (const s of sets?.traitsets || []) map[s.id] = s.name
      const ids = (sets?.traitsets || []).map((s) => s.id)
      if (ids.length) {
        const traits = await graphql(TRAITS_BY_TRAITSETS, { ids }).catch(() => null)
        for (const t of traits?.traitsByTraitsets || []) map[t.id] = t.name
      }
      // Universes are keyed *and* id'd (a projection is scoped by key, a target
      // may name the entity), so both spellings go in.
      await universes.load()
      for (const [k, v] of Object.entries(universes.names.value || {})) map[k] = v
      // Effect action labels are half of an effect's phrase; load them together
      // so no host has to remember a second call.
      await loadActions().catch(() => null)

      names.value = map
      loaded = true
      return map
    })().finally(() => { pending = null })
    return pending
  }

  /**
   * id → label. Falls back to a live entity name from the shared cache, then to
   * the id itself. Never returns `undefined`, so a caller cannot accidentally
   * render "undefined" where it meant to render an id.
   */
  function resolve(id) {
    if (id === null || id === undefined || id === '') return ''
    const s = String(id)
    if (names.value[s]) return names.value[s]
    const live = cache.state.entities[s]
    if (live && live.data && live.data.name) return live.data.name
    return s
  }

  /** True when the id is *not* registry-known — the surface dims these. */
  function known(id) {
    return !!(id && names.value[String(id)])
  }

  return {
    names, loaded, load, resolve, known,
    /** Bound row vocabulary — the phrasing every surface renders. */
    key: (entry, index, scheme) => entryKey(entry, index, scheme),
    condition: (c) => conditionSummary(c, resolve),
    effect: (e) => effectSummary(e, { labelFor, resolve }),
    cost: (costEffects) => costSummary(costEffects, (e) => effectSummary(e, { labelFor, resolve })),
  }
}
