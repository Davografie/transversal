import { ref } from 'vue'
import { useApi } from './useApi.js'

// ── Module-level singleton state ─────────────────────
// All components sharing this composable read/write the same refs.
const ownersByType = ref({})   // { [ownerType]: [{ ownerType, ownerId, label, sfxIds }] }
const loading = ref(false)
const error = ref('')

// GraphQL enum names for each owner surface (see SfxOwnerKind in types.py).
export const OWNER_TYPES = [
  { value: 'TABLE', label: 'Table', hint: 'everyone' },
  { value: 'GM', label: 'GM', hint: 'GM-context (manage-only for now)' },
  { value: 'ENTITY', label: 'Entity', hint: 'characters, factions, GMCs, assets, universes' },
  { value: 'LOCATION', label: 'Location', hint: 'a place — its rules reach whoever is inside' },
  { value: 'PROJECTION', label: 'Projection', hint: 'body' },
  { value: 'TRAIT', label: 'Trait', hint: 'trait definition default SFX' },
  { value: 'TRAIT_INSTANCE', label: 'Trait instance', hint: 'entity↔trait setting' },
  { value: 'TRAIT_SET', label: 'Trait set', hint: 'entity↔traitset setting' },
]

export function useSfxOwners() {
  const { graphql, error: apiError } = useApi()

  async function fetchOwners(ownerType) {
    loading.value = true
    error.value = ''
    const res = await graphql(
      `query($ownerType: SfxOwnerKind!) {
        sfxOwners(ownerType: $ownerType) { ownerType ownerId label sfxIds }
      }`,
      { ownerType }
    )
    if (res?.sfxOwners) ownersByType.value[ownerType] = res.sfxOwners
    loading.value = false
    return res?.sfxOwners || []
  }

  async function addOwnerSfx(ownerRefs, sfxId) {
    const res = await graphql(
      `mutation($ownerRefs: [OwnerRefInput!]!, $sfxId: ID!) { addOwnerSfx(ownerRefs: $ownerRefs, sfxId: $sfxId) }`,
      { ownerRefs, sfxId }
    )
    if (res?.addOwnerSfx !== true) {
      error.value = apiError.value || 'Add failed'
      return false
    }
    _patchLocal(ownerRefs, sfxId, 'add')
    return true
  }

  async function removeOwnerSfx(ownerRefs, sfxId) {
    const res = await graphql(
      `mutation($ownerRefs: [OwnerRefInput!]!, $sfxId: ID!) { removeOwnerSfx(ownerRefs: $ownerRefs, sfxId: $sfxId) }`,
      { ownerRefs, sfxId }
    )
    if (res?.removeOwnerSfx !== true) {
      error.value = apiError.value || 'Remove failed'
      return false
    }
    _patchLocal(ownerRefs, sfxId, 'remove')
    return true
  }

  function _patchLocal(ownerRefs, sfxId, mode) {
    for (const ref of ownerRefs) {
      const list = ownersByType.value[ref.ownerType] || []
      const owner = list.find(o => o.ownerId === ref.ownerId)
      if (!owner) continue
      if (mode === 'add') {
        if (!owner.sfxIds.includes(sfxId)) owner.sfxIds.push(sfxId)
      } else {
        owner.sfxIds = owner.sfxIds.filter(id => id !== sfxId)
      }
    }
  }

  return { ownersByType, loading, error, OWNER_TYPES, fetchOwners, addOwnerSfx, removeOwnerSfx }
}
