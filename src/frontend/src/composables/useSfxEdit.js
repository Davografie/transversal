import { reactive, ref, watch } from 'vue'
import { useApi } from './useApi.js'
import { useTraitsConfig } from './useTraitsConfig.js'

// ── SFX-edit state, one instance per editor panel ─────────────
// Every ref lives inside the factory. GmSfxEditPanel owns an instance and
// provides it to its GmEffectEditPanel child (Rule 2 — no prop-drilling the
// effects array; Rule 6 — identity only), so that pair shares one draft while
// two open editors keep their own. They used to share one module-level draft:
// opening a second SFX inside a detached editor re-pointed the first, and a
// save from either panel wrote to whichever SFX was opened last.
// (The query constants and generateSfxId stay at module level.)
export function generateSfxId(name) {
  return 'sfx-' + name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

export function createSfxEdit() {
  const sfxId = ref(null)
  const draft = reactive({
    name: '',
    description: '',
    trigger: 'manual',
    source_kind: null,
    placement: null,
    arming_scope: null,   // null = auto (derive from trigger)
    listener_spec: { steps: [] },
    acquire_spec: { steps: [] },
    // Values the rule names and resolves for itself, before the conditions run.
    // Read back from the server so a save round-trips them (an omitted field is a
    // deleted section).
    bound_variables: [],
    conditions: [],
    effects: [],
    duration: { timers: [{ event: 'rolls', remaining: 1 }], combine: 'FIRST_TO_FIRE' },
  })
  const saving = ref(false)
  const errorMsg = ref('')
  const successMsg = ref('')
  const savedAt = ref(null)
  const validationWarnings = ref([])
  const scopeVariables = ref([])
  // Derived rules text for the current draft ([[SFX Natural Language Plan]]).
  const cardText = ref('')

const UPDATE_MUTATION = `mutation($input: SfxUpdateInput!) { updateSfx(input: $input) { id name description trigger sourceKind placement armingScope listenerSpec acquireSpec limit boundVariables { name spec } conditions { type subject target targets value operator narrative spec } effects { timing type action target entity result dieFilter negative context duration { timers { event remaining } combine } targetSpec entitySpec resultSpec ownerSpec refs output conditions { type subject target targets value operator narrative spec } } duration { timers { event remaining } combine } } }`
const CREATE_MUTATION = `mutation($input: SfxInput!) { createSfx(input: $input) { id name description trigger sourceKind placement armingScope listenerSpec acquireSpec limit boundVariables { name spec } conditions { type subject target targets value operator narrative spec } effects { timing type action target entity result dieFilter negative context duration { timers { event remaining } combine } targetSpec entitySpec resultSpec ownerSpec refs output conditions { type subject target targets value operator narrative spec } } duration { timers { event remaining } combine } } }`
const VALIDATE_QUERY = `query($input: SfxInput!) { validateSfx(input: $input) }`
// Derived rules text for an *unsaved* draft — the SFX editor's live card preview.
const SFX_TEXT_QUERY = `query($sfx: SfxInput!) { sfxText(sfx: $sfx) }`
const SCOPE_VARS_QUERY = `query($trigger: String, $sourceKind: String) { scopeVariables(trigger: $trigger, sourceKind: $sourceKind) { name type } }`

function initialConditions(sfx) {
  if (sfx?.conditions?.length) {
    return sfx.conditions.map(c => ({
      type: c.type || 'ALWAYS',
      subject: c.subject || '',
      target: c.target || '',
      value: c.value || '',
      operator: c.operator || '>=',
      narrative: c.narrative || '',
      spec: c.spec || { steps: [] },
    }))
  }
  if (sfx?.limit) {
    return [{ type: 'NARRATIVE', subject: '', target: '', value: '', narrative: sfx.limit }]
  }
  return []
}

function initialDuration(sfx) {
  // Backend default = rolls:1; null = indefinite (empty timers).
  if (sfx && sfx.duration) {
    return {
      timers: (sfx.duration.timers || []).map(t => ({ event: t.event, remaining: t.remaining })),
      combine: sfx.duration.combine || 'FIRST_TO_FIRE',
    }
  }
  if (sfx && sfx.duration === null) {
    return { timers: [], combine: 'FIRST_TO_FIRE' }
  }
  return { timers: [{ event: 'rolls', remaining: 1 }], combine: 'FIRST_TO_FIRE' }
}

  let _saveTimer = null
  let _validationTimer = null
  let _suppressEdits = false

  const { graphql, error: apiError } = useApi()
  const { patchData, fetchTraitsConfig } = useTraitsConfig()

  function open(sfx) {
    // Loading a record is not an edit, so any write queued against the *previous*
    // state is dropped. Otherwise a pending auto-save fires after the reload and
    // persists the freshly-loaded (older) values over the ones just written —
    // which is how adding an effect ended up saving an empty effect list.
    clearTimeout(_saveTimer)
    clearTimeout(_validationTimer)
    // Initializing the draft must not read as a user edit (else open triggers a
    // spurious auto-save/validate). Watchers are sync-flushed and check this flag.
    _suppressEdits = true
    sfxId.value = sfx?.id || null
    draft.name = sfx?.name || ''
    draft.description = sfx?.description || ''
    draft.trigger = sfx?.trigger || 'manual'
    draft.source_kind = sfx?.sourceKind ?? sfx?.source_kind ?? null
    draft.placement = sfx?.placement ?? null
    draft.arming_scope = sfx?.armingScope ?? sfx?.arming_scope ?? null
    draft.listener_spec = sfx?.listenerSpec ?? sfx?.listener_spec ?? { steps: [] }
    draft.acquire_spec = sfx?.acquireSpec ?? sfx?.acquire_spec ?? { steps: [] }
    draft.bound_variables = (sfx?.boundVariables ?? sfx?.bound_variables ?? [])
      .map(bv => ({ name: bv.name || '', spec: bv.spec || { steps: [] } }))
    draft.conditions = initialConditions(sfx)
    draft.duration = initialDuration(sfx)
    draft.effects = (sfx?.effects || []).map(e => ({ ...e }))
    savedAt.value = null
    errorMsg.value = ''
    successMsg.value = ''
    validationWarnings.value = []
    _suppressEdits = false
    fetchScopeVariables(draft.trigger, draft.source_kind)
    previewText()
  }

  function reset() {
    draft.name = ''
    draft.description = ''
    draft.trigger = 'manual'
    draft.source_kind = null
    draft.placement = null
    draft.arming_scope = null
    draft.listener_spec = { steps: [] }
    draft.acquire_spec = { steps: [] }
    draft.bound_variables = []
    draft.conditions = []
    draft.duration = { timers: [{ event: 'rolls', remaining: 1 }], combine: 'FIRST_TO_FIRE' }
    draft.effects = []
    cardText.value = ''
  }

  async function fetchScopeVariables(trigger = '', sourceKind = null) {
    try {
      const data = await graphql(SCOPE_VARS_QUERY, { trigger: trigger || '', sourceKind: sourceKind || null })
      scopeVariables.value = data?.scopeVariables || []
    } catch {
      scopeVariables.value = []
    }
  }

  // The stateless payload both draft queries send (validate + card text).
  function draftInput() {
    return {
      id: sfxId.value || 'sfx-draft',
      name: draft.name || 'Draft',
      trigger: draft.trigger,
      sourceKind: draft.source_kind || null,
      placement: draft.placement || null,
      armingScope: draft.arming_scope || null,
      listenerSpec: (draft.listener_spec?.steps?.length) ? draft.listener_spec : null,
              acquireSpec: (draft.acquire_spec?.steps?.length) ? draft.acquire_spec : null,
      boundVariables: (draft.bound_variables || [])
        .filter(bv => (bv.name || '').trim() && (bv.spec?.steps?.length)),
      conditions: draft.conditions || [],
      effects: draft.effects || [],
      duration: draft.duration,
    }
  }

  async function validate() {
    try {
      const data = await graphql(VALIDATE_QUERY, { input: draftInput() })
      validationWarnings.value = data?.validateSfx || []
    } catch {
      validationWarnings.value = []
    }
  }

  async function previewText() {
    try {
      const data = await graphql(SFX_TEXT_QUERY, { sfx: draftInput() })
      cardText.value = data?.sfxText || ''
    } catch {
      cardText.value = ''
    }
  }

  async function save() {
    if (!sfxId.value) return false
    saving.value = true
    errorMsg.value = ''
    try {
      const result = await graphql(UPDATE_MUTATION, {
        input: {
          id: sfxId.value, name: draft.name, trigger: draft.trigger, description: draft.description,
          sourceKind: draft.source_kind || null, placement: draft.placement || null,
          armingScope: draft.arming_scope || null,
          listenerSpec: (draft.listener_spec?.steps?.length) ? draft.listener_spec : null,
              acquireSpec: (draft.acquire_spec?.steps?.length) ? draft.acquire_spec : null,
          boundVariables: (draft.bound_variables || []).filter(bv => (bv.name || '').trim() && (bv.spec?.steps?.length)),
          conditions: draft.conditions, effects: draft.effects, duration: draft.duration,
        },
      })
      if (!result) { errorMsg.value = apiError.value || 'Save failed'; return false }
      patchData('sfxs', sfxId.value, {
        // ⚠ The keys must match what the `sfxs` query returns (camelCase). A
        // snake_case key here does not *replace* the query's value — it sits
        // beside it, and the camelCase one wins on the next read. That is how a
        // just-saved bound variable came back empty after closing and reopening
        // the editor: `boundVariables` still held the value from the last fetch
        // while the fresh edit went to `bound_variables`. Same trap for
        // sourceKind / armingScope / listenerSpec / acquireSpec.
        name: draft.name, trigger: draft.trigger, description: draft.description,
        sourceKind: draft.source_kind, placement: draft.placement,
        armingScope: draft.arming_scope, listenerSpec: draft.listener_spec,
        acquireSpec: draft.acquire_spec,
        boundVariables: (draft.bound_variables || []).map(bv => ({ ...bv })),
        conditions: [...draft.conditions], duration: draft.duration, effects: [...draft.effects],
      })
      savedAt.value = Date.now()
      return true
    } finally { saving.value = false }
  }

  async function create() {
    saving.value = true
    errorMsg.value = ''
    const id = generateSfxId(draft.name)
    try {
      const result = await graphql(CREATE_MUTATION, {
        input: {
          id, name: draft.name.trim(), trigger: draft.trigger, description: draft.description,
          sourceKind: draft.source_kind || null, placement: draft.placement || null,
          armingScope: draft.arming_scope || null,
          listenerSpec: (draft.listener_spec?.steps?.length) ? draft.listener_spec : null,
              acquireSpec: (draft.acquire_spec?.steps?.length) ? draft.acquire_spec : null,
          boundVariables: (draft.bound_variables || []).filter(bv => (bv.name || '').trim() && (bv.spec?.steps?.length)),
          conditions: draft.conditions, effects: draft.effects, duration: draft.duration,
        },
      })
      if (!result) {
        const msg = apiError.value || ''
        if (msg.includes('unique constraint') || msg.includes('already exists') || msg.includes('conflicting key')) {
          errorMsg.value = `"${draft.name}" already exists — close and re-open the trait to see it`
        } else {
          errorMsg.value = msg || 'Create failed'
        }
        return false
      }
      errorMsg.value = ''
      await fetchTraitsConfig()
      patchData('sfxs', id, {
        // Same key discipline as `save()` above: mirror the query's shape.
        id, name: draft.name.trim(), trigger: draft.trigger, description: draft.description,
        sourceKind: draft.source_kind, placement: draft.placement,
        armingScope: draft.arming_scope, listenerSpec: draft.listener_spec,
        acquireSpec: draft.acquire_spec,
        boundVariables: (draft.bound_variables || []).map(bv => ({ ...bv })),
        conditions: [...draft.conditions], duration: draft.duration, effects: [...draft.effects],
      })
      successMsg.value = `Created "${draft.name}"`
      return id
    } finally { saving.value = false }
  }

  async function remove() {
    if (!sfxId.value) return false
    saving.value = true
    try {
      await graphql(`mutation($id: ID!) { deleteSfx(id: $id) }`, { id: sfxId.value })
      await fetchTraitsConfig()
      return true
    } finally { saving.value = false }
  }

  // One set of watchers per instance, following this instance's draft. Sync
  // flush lets `open()` suppress the initial assignment via `_suppressEdits`.
  watch(() => [draft.trigger, draft.source_kind], ([t, sk]) => {
    if (_suppressEdits) return
    fetchScopeVariables(t || '', sk || null)
  }, { flush: 'sync' })
  watch(() => [draft.trigger, draft.source_kind, draft.arming_scope, draft.listener_spec, draft.conditions, draft.effects], () => {
    if (_suppressEdits) return
    clearTimeout(_validationTimer)
    _validationTimer = setTimeout(() => { validate(); previewText() }, 400)
  }, { deep: true, flush: 'sync' })
  watch(
    () => [draft.name, draft.description, draft.trigger, draft.source_kind, draft.placement, draft.arming_scope, draft.listener_spec, draft.conditions, draft.duration, draft.effects],
    () => {
      if (_suppressEdits) return
      if (!sfxId.value) return
      savedAt.value = null
      clearTimeout(_saveTimer)
      _saveTimer = setTimeout(save, 700)
    },
    { deep: true, flush: 'sync' },
  )

  return {
    sfxId, draft, saving, errorMsg, successMsg, savedAt, validationWarnings, scopeVariables, cardText,
    open, reset, save, create, remove, validate, previewText, fetchScopeVariables,
  }
}
