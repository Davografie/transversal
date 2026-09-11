import { computed, ref } from 'vue'
import { usePersistedRef } from './usePersistedState.js'

/**
 * The character sheet's inline trait editor: the draft state behind the
 * full-panel editor, the persistence calls, and the little interactions that
 * surround them (EGO/morph, projection, SFX chips, sub-traits, the delete
 * countdown, spent-die recovery).
 *
 * The draft lives in `usePersistedRef('sheet.*')` on purpose — a standby-to-wake
 * reload restores whatever the user was editing. The sheet owns the data it
 * edits, so everything it touches is injected rather than imported:
 *
 *   props                the sheet's props (entityId, universe, …)
 *   entity               ref — the fetched entity (projections, razmerit)
 *   traitSets            ref — [{ name, limit, traits }] as rendered
 *   profileTraits        ref — EMPTY-rated traits, rendered in the profile tab
 *   detailTrait          ref — the read-only detail view (cleared on edit)
 *   graphql              query helper from useApi
 *   fetchEntity          reload the entity after anchor-changing edits
 *   recomputeTraitSets   re-split the tab lists after a rating-type change
 *   recoverResourceDie   REST helper for pulling a spent die back
 *   universeDisplay      universe key → display name (for the projection chip)
 */
export function useTraitEditor({
  props,
  entity,
  traitSets,
  profileTraits,
  detailTrait,
  graphql,
  fetchEntity,
  recomputeTraitSets,
  recoverResourceDie,
  universeDisplay,
}) {
  // Trait editing (full-panel view)
  const editingTraitId = usePersistedRef('sheet.editTraitId', null)

  // trait id → display name, for resolving possible sub-trait candidates.
  const traitNameMap = ref({})
  async function ensureTraitNames() {
    if (Object.keys(traitNameMap.value).length) return
    try {
      const data = await graphql(`query($u: String!) { traitsByUniverse(universe: $u) { id name } }`, { u: props.universe })
      const m = {}
      for (const t of (data?.traitsByUniverse || [])) m[t.id] = t.name
      traitNameMap.value = m
    } catch { /* leave map empty; candidates fall back to slug names */ }
  }

  const editingTrait = computed(() => {
    if (!editingTraitId.value) return null
    for (const ts of traitSets.value) {
      const t = ts.traits.find(t => t.id === editingTraitId.value)
      if (t) return t
    }
    return profileTraits.value.find(t => t.id === editingTraitId.value) || null
  })

  function slugTraitId(id) {
    return String(id).replace(/^trait-/, '').replace(/-[a-z0-9]{4}$/i, '').replace(/-/g, ' ')
  }

  const availableSubtraits = computed(() => {
    const assigned = new Set((editingTrait.value?.subTraitSettings || []).map(st => st.traitId))
    return (editingTrait.value?.possibleSubtraitIds || [])
      .filter(id => !assigned.has(id))
      .map(id => ({ id, name: traitNameMap.value[id] || slugTraitId(id) }))
  })

  const editDice = usePersistedRef('sheet.editDice', [])
  const editRatingType = usePersistedRef('sheet.editRatingType', 'STATIC')
  const editPolarity = usePersistedRef('sheet.editPolarity', null)
  const editCapacity = usePersistedRef('sheet.editCapacity', [])
  const editStatement = usePersistedRef('sheet.editStatement', '')
  const editNotes = usePersistedRef('sheet.editNotes', '')
  const editSfxIds = usePersistedRef('sheet.editSfxIds', [])
  const editIsEgo = usePersistedRef('sheet.editIsEgo', true)
  const editProjectionId = usePersistedRef('sheet.editProjectionId', null)
  const showProjectionPicker = ref(false)

  // The rules this trait instance may actually take *here* — the subset of its
  // possible SFX whose acquire gate resolves right now (`acquirableSfxIds`).
  // `null` means "not answered yet", which the panel reads as "show them all";
  // the attach enforces the gate server-side either way, so a preview must not
  // be the thing the user relies on.
  const acquirableSfxIds = ref(null)

  async function fetchAcquirableSfxIds(traitSettingId) {
    acquirableSfxIds.value = null
    if (!traitSettingId) return
    try {
      const data = await graphql(
        `query($id: ID!) { acquirableSfxIds(traitSettingId: $id) }`,
        { id: traitSettingId },
      )
      acquirableSfxIds.value = data?.acquirableSfxIds ?? null
    } catch (e) {
      // Stay `null` (full list) rather than hide chips on a failed query — the
      // server still refuses an attach that isn't allowed here.
      console.error('acquirableSfxIds failed:', e)
      acquirableSfxIds.value = null
    }
  }

  const editProjectionOptions = computed(() => entity.value?.projections || [])
  const editProjectionName = computed(() => {
    const p = editProjectionOptions.value.find((p) => p.id === editProjectionId.value)
    return p ? (p.name || universeDisplay(p.originUniverse)) : (editProjectionId.value || 'select projection')
  })

  const deleteCountdown = ref(0)
  const deletingTraitId = ref(null)
  let deleteTimer = null

  function startEdit(t) {
    if (deleteCountdown.value > 0) {
      clearInterval(deleteTimer)
      deleteCountdown.value = 0
      const targetId = deletingTraitId.value
      deletingTraitId.value = null
      deleteTrait({ id: targetId })
    }
    editingTraitId.value = t.id
    detailTrait.value = null
    fetchAcquirableSfxIds(t.id)
    ensureTraitNames()
    editDice.value = (t.dice || []).map(d => d.toLowerCase())
    editCapacity.value = (t.capacity || []).map(d => d.toLowerCase())
    editRatingType.value = t.ratingType || 'STATIC'
    editPolarity.value = t.polarity || null
    editStatement.value = t.statement || ''
    editNotes.value = t.notes || ''
    editSfxIds.value = [...(t.sfxIds || [])]
    const isMorph = t.fromType === 'projection' || t.ego === false
    editIsEgo.value = !isMorph
    editProjectionId.value =
      (t.fromType === 'projection' && t.projectionId) ||
      (isMorph ? (entity.value?.currentProjection || entity.value?.projections?.[0]?.id) : null) ||
      null
    showProjectionPicker.value = false
  }

  function cancelEdit() {
    if (deleteCountdown.value > 0) {
      clearInterval(deleteTimer)
      deleteCountdown.value = 0
      const targetId = deletingTraitId.value
      deletingTraitId.value = null
      deleteTrait({ id: targetId })
    } else {
      editingTraitId.value = null
    }
  }

  function onDeleteClick(t) {
    if (deleteCountdown.value > 0) {
      clearInterval(deleteTimer)
      deleteCountdown.value = 0
      deletingTraitId.value = null
      return
    }
    deleteCountdown.value = 3
    deletingTraitId.value = t.id
    deleteTimer = setInterval(() => {
      deleteCountdown.value--
      if (deleteCountdown.value <= 0) {
        clearInterval(deleteTimer)
        deletingTraitId.value = null
        deleteTrait(t)
      }
    }, 1000)
  }

  async function deleteTrait(t) {
    await fetch('/api/v1/graphql', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: `mutation($id: ID!) { removeTraitSetting(id: $id) }`, variables: { id: t.id } }),
    })
    editingTraitId.value = null
    // Remove from local traitSets / profileTraits — no full re-render
    let removed = false
    for (const ts of traitSets.value) {
      const idx = ts.traits.findIndex(tr => tr.id === t.id)
      if (idx !== -1) {
        ts.traits.splice(idx, 1)
        if (ts.traits.length === 0) {
          traitSets.value = traitSets.value.filter(s => s.name !== ts.name)
        }
        removed = true
        break
      }
    }
    if (!removed) {
      const idx = profileTraits.value.findIndex(tr => tr.id === t.id)
      if (idx !== -1) profileTraits.value.splice(idx, 1)
    }
  }

  function ensureEditProjection() {
    if (!editIsEgo.value && !editProjectionId.value) {
      editProjectionId.value = entity.value?.currentProjection || entity.value?.projections?.[0]?.id || null
    }
  }

  async function doSave() {
    if (!editingTraitId.value) return
    ensureEditProjection()
    const isRel = editingTrait.value?.fromType === 'relationship'
    const newDice = editDice.value.map(d => d.toUpperCase())
    const newCapacity = editCapacity.value.map(d => d.toUpperCase())
    const query = `mutation($id: ID!, $dice: [DieType!], $capacity: [DieType!], $ratingType: RatingType, $polarity: Polarity, $statement: String, $notes: String, $sfxIds: [ID!], $fromType: String, $projectionId: ID) {
    updateTraitSetting(id: $id, input: { dice: $dice, capacity: $capacity, ratingType: $ratingType, polarity: $polarity, statement: $statement, notes: $notes, sfxIds: $sfxIds, fromType: $fromType, projectionId: $projectionId }) { id }
  }`
    const variables = {
      id: editingTraitId.value,
      dice: newDice,
      capacity: newCapacity,
      ratingType: editRatingType.value,
      polarity: editPolarity.value,
      statement: editStatement.value ?? null,
      notes: editNotes.value ?? null,
      sfxIds: editSfxIds.value,
      // Relationship traits keep their anchor; only entity/projection traits toggle it.
      fromType: isRel ? null : (editIsEgo.value ? 'entity' : 'projection'),
      projectionId: isRel ? null : (editIsEgo.value ? null : editProjectionId.value),
    }
    await fetch('/api/v1/graphql', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, variables }),
    })
    // Patch local data — no full re-render
    const patchTrait = (t) => {
      t.dice = newDice
      t.capacity = newCapacity
      t.ratingType = editRatingType.value
      t.polarity = editPolarity.value
      t.rating = null  // force fallback to dice display
      t.sfxIds = [...editSfxIds.value]
      t.statement = editStatement.value
      t.notes = editNotes.value
      if (!isRel) {
        t.ego = editIsEgo.value
        t.fromType = editIsEgo.value ? 'entity' : 'projection'
        t.projectionId = editIsEgo.value ? null : editProjectionId.value
      }
    }
    for (const ts of traitSets.value) {
      const t = ts.traits.find(t => t.id === editingTraitId.value)
      if (t) { patchTrait(t); break }
    }
    const pt = profileTraits.value.find(t => t.id === editingTraitId.value)
    if (pt) patchTrait(pt)
  }

  async function toggleEgo() {
    editIsEgo.value = !editIsEgo.value
    if (!editIsEgo.value) {
      editProjectionId.value = entity.value?.currentProjection || entity.value?.projections?.[0]?.id || null
    }
    showProjectionPicker.value = false
    await doSave()
    await fetchEntity()
  }

  function togglePolarity() {
    editPolarity.value = editPolarity.value === 'POSITIVE' ? 'NEGATIVE' : 'POSITIVE'
    doSave()
  }

  function toggleProjectionPicker() {
    showProjectionPicker.value = !showProjectionPicker.value
  }

  async function selectProjection(p) {
    editProjectionId.value = p.id
    showProjectionPicker.value = false
    await doSave()
    await fetchEntity()
  }

  function toggleSfx(sfxId) {
    const idx = editSfxIds.value.indexOf(sfxId)
    if (idx === -1) editSfxIds.value.push(sfxId)
    else editSfxIds.value.splice(idx, 1)
    doSave()
  }

  // --- shared trait editor (components/ui/TraitInstanceEditor.vue) ----------
  // The editor is controlled: it emits field updates and a `change` event naming
  // the field, and the sheet owns persistence (it saves live, like before).
  async function onEditorRatingType(rt) {
    editRatingType.value = rt
    // EMPTY traits carry no dice rating — clear them.
    if (rt === 'EMPTY') editDice.value = []
    await doSave()
    // Re-split so the trait moves between the rated list and the profile tab.
    recomputeTraitSets()
  }

  function onEditorChange(field) {
    if (field === 'ratingType') return                                    // onEditorRatingType owns this path
    if (field === 'statement' || field === 'notes') return onStatementInput()  // debounced, as before
    doSave()                                                              // dice, capacity, polarity
  }

  function onEditorFieldBlur(field) {
    if (field === 'statement') splitStatement()
  }

  async function addSubTrait(traitId) {
    const parentId = editingTrait.value?.id
    if (!parentId) return
    await graphql(`mutation($parent: ID!, $trait: ID!) { addSubTrait(parentTraitsettingId: $parent, traitId: $trait) { id } }`, { parent: parentId, trait: traitId })
    await fetchEntity()
  }

  async function removeSubTrait(subId) {
    await graphql(`mutation($id: ID!) { removeSubTrait(subTraitSettingId: $id) }`, { id: subId })
    await fetchEntity()
  }

  let statementDebounce = null
  function onStatementInput() {
    clearTimeout(statementDebounce)
    statementDebounce = setTimeout(doSave, 500)
  }

  function splitStatement() {
    const words = (editStatement.value || '').trim().split(/\s+/).filter(Boolean)
    if (words.length > 7) {
      const moved = editStatement.value.trim()
      editNotes.value = editNotes.value ? editNotes.value + '\n' + moved : moved
      editStatement.value = ''
    }
  }

  async function recoverSpentDie(die) {
    // Recover one spent die back into the resource pool (editor affordance).
    // Patch local state from the REST response so both the recoverable row
    // and the available-dice chips update without a full refetch.
    const t = editingTrait.value
    if (!t) return
    const res = await recoverResourceDie(t.id, die.toLowerCase())
    if (!res) return
    const toUpper = (arr) => (arr || []).map((d) => d.toUpperCase())
    t.dice = toUpper(res.dice)
    t.spentDice = toUpper(res.spent)
    t.rating = null  // force fallback to dice display
    editDice.value = (res.dice || []).map((d) => d.toLowerCase())
  }

  return {
    // state
    editingTraitId, editingTrait, availableSubtraits,
    editDice, editRatingType, editPolarity, editCapacity, editStatement, editNotes,
    editSfxIds, editIsEgo, editProjectionId, showProjectionPicker,
    acquirableSfxIds,
    editProjectionOptions, editProjectionName,
    deleteCountdown, deletingTraitId,
    // actions
    startEdit, cancelEdit, onDeleteClick, doSave,
    toggleEgo, togglePolarity, toggleProjectionPicker, selectProjection, toggleSfx,
    onEditorRatingType, onEditorChange, onEditorFieldBlur,
    addSubTrait, removeSubTrait, onStatementInput, splitStatement, recoverSpentDie,
    ensureTraitNames,
  }
}
