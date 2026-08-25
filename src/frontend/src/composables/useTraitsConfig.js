import { ref, computed } from 'vue'
import { useApi } from './useApi.js'

// ── Module-level singleton state ─────────────────────
// All components sharing this composable read/write the same refs.
const traitsets = ref([])
const allSfxs = ref([])
const loading = ref(false)

export function useTraitsConfig() {
  const { graphql } = useApi()

  // ── Fetch ──────────────────────────────────────────
  async function fetchTraitsConfig() {
    loading.value = true
    const [ts, sf] = await Promise.all([
      graphql(`query {
        traitsets {
          id name universes entityTypes order limit polarity
          traits {
            id name defaultDieType traitsetId universes
            locationRestricted defaultEgo polarity
            possibleSfxIds defaultSfxIds
            displayNames { name universe ratings }
          }
        }
      }`),
      graphql(`query {
        sfxs {
          id name description trigger limit
          conditions { type target value narrative }
          effects { timing type action target entity result targetScope entityScope targetFilter negative context duration { timers { event remaining } combine } }
        }
      }`),
    ])
    if (ts?.traitsets) traitsets.value = ts.traitsets
    if (sf?.sfxs) allSfxs.value = sf.sfxs
    loading.value = false
  }

  // ── Optimistic local patch ─────────────────────────
  // Used by sub-panels after mutations so the UI updates instantly
  // without waiting for a full re-fetch.
  function patchData(collection, id, changes) {
    let arr
    if (collection === 'traitsets') {
      arr = traitsets
    } else if (collection === 'traits') {
      for (const ts of traitsets.value) {
        const idx = (ts.traits || []).findIndex(t => t.id === id)
        if (idx >= 0) {
          Object.assign(ts.traits[idx], changes)
          ts.traits[idx]._flash = (ts.traits[idx]._flash || 0) + 1
          setTimeout(() => { if (ts.traits[idx]._flash) ts.traits[idx]._flash = 0 }, 600)
          break
        }
      }
      return
    } else if (collection === 'sfxs') {
      arr = allSfxs
    }
    if (arr) {
      const idx = arr.value.findIndex(item => item.id === id)
      if (idx >= 0) {
        Object.assign(arr.value[idx], changes)
        arr.value[idx]._flash = (arr.value[idx]._flash || 0) + 1
        setTimeout(() => { if (arr.value[idx]._flash) arr.value[idx]._flash = 0 }, 600)
      } else if (changes.id) {
        // New item — push it
        arr.value.push({ ...changes, _flash: 1 })
        setTimeout(() => {
          const newIdx = arr.value.findIndex(item => item.id === id)
          if (newIdx >= 0 && arr.value[newIdx]._flash) arr.value[newIdx]._flash = 0
        }, 600)
      }
    }
  }

  // ── Batch update ───────────────────────────────────
  // Applies the same partial `changes` (a TraitUpdateInput-shaped object
  // with only the fields to set) to many trait definitions in parallel.
  async function batchUpdateTraits(ids, changes) {
    const results = await Promise.allSettled(ids.map((id) =>
      graphql(
        `mutation($id: ID!, $input: TraitUpdateInput!) { updateTrait(id: $id, input: $input) { id } }`,
        { id, input: changes },
      )
    ))
    // Local patch must mirror the real data fields only; input-only flags
    // (clearPolarity) are stripped and translated to the resulting value.
    const patch = { ...changes }
    if ('clearPolarity' in patch) {
      delete patch.clearPolarity
      patch.polarity = null
    }
    const succeeded = []
    const failed = []
    results.forEach((r, i) => {
      if (r.status === 'fulfilled') {
        succeeded.push(ids[i])
        patchData('traits', ids[i], patch)
      } else {
        failed.push(ids[i])
      }
    })
    return { succeeded, failed }
  }

  // ── Derived ────────────────────────────────────────
  const traitNameMap = computed(() => {
    const m = {}
    for (const ts of traitsets.value) {
      for (const t of (ts.traits || [])) {
        m[t.id] = t.name
      }
    }
    return m
  })

  return {
    traitsets,
    allSfxs,
    loading,
    fetchTraitsConfig,
    patchData,
    batchUpdateTraits,
    traitNameMap,
  }
}
