import { reactive, ref, watch } from 'vue'
import { useApi } from './useApi.js'
import { useTraitsConfig } from './useTraitsConfig.js'

// ── Shared SFX-edit state (module-level singleton) ─────────────
// One SFX is edited at a time across the panel stack: GmSfxEditPanel owns the
// draft, and the GmEffectEditPanel child panel reads/writes the same reactive
// state (Rule 2 — no prop-drilling the effects array; Rule 6 — identity only).
const sfxId = ref(null)
const draft = reactive({
  name: '',
  description: '',
  trigger: 'manual',
  source_kind: null,
  placement: null,
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

const UPDATE_MUTATION = `mutation($input: SfxUpdateInput!) { updateSfx(input: $input) { id name description trigger sourceKind placement limit conditions { type subject target value operator narrative spec } effects { timing type action target entity result targetScope entityScope targetFilter dieFilter negative context duration { timers { event remaining } combine } targetSpec entitySpec refs conditions { type subject target value operator narrative spec } } duration { timers { event remaining } combine } } }`
const CREATE_MUTATION = `mutation($input: SfxInput!) { createSfx(input: $input) { id name description trigger sourceKind placement limit conditions { type subject target value operator narrative spec } effects { timing type action target entity result targetScope entityScope targetFilter dieFilter negative context duration { timers { event remaining } combine } targetSpec entitySpec refs conditions { type subject target value operator narrative spec } } duration { timers { event remaining } combine } } }`
const VALIDATE_QUERY = `query($input: SfxInput!) { validateSfx(input: $input) }`
const SCOPE_VARS_QUERY = `query($trigger: String, $sourceKind: String) { scopeVariables(trigger: $trigger, sourceKind: $sourceKind) { name type } }`

export function generateSfxId(name) {
  return 'sfx-' + name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

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

let _watchersSetup = false
let _saveTimer = null
let _validationTimer = null
let _suppressEdits = false

export function useSfxEdit() {
  const { graphql, error: apiError } = useApi()
  const { patchData, fetchTraitsConfig } = useTraitsConfig()

  function open(sfx) {
    // Initializing the draft must not read as a user edit (else open triggers a
    // spurious auto-save/validate). Watchers are sync-flushed and check this flag.
    _suppressEdits = true
    sfxId.value = sfx?.id || null
    draft.name = sfx?.name || ''
    draft.description = sfx?.description || ''
    draft.trigger = sfx?.trigger || 'manual'
    draft.source_kind = sfx?.sourceKind ?? sfx?.source_kind ?? null
    draft.placement = sfx?.placement ?? null
    draft.conditions = initialConditions(sfx)
    draft.duration = initialDuration(sfx)
    draft.effects = (sfx?.effects || []).map(e => ({ ...e }))
    savedAt.value = null
    errorMsg.value = ''
    successMsg.value = ''
    validationWarnings.value = []
    _suppressEdits = false
    fetchScopeVariables(draft.trigger, draft.source_kind)
  }

  function reset() {
    draft.name = ''
    draft.description = ''
    draft.trigger = 'manual'
    draft.source_kind = null
    draft.placement = null
    draft.conditions = []
    draft.duration = { timers: [{ event: 'rolls', remaining: 1 }], combine: 'FIRST_TO_FIRE' }
    draft.effects = []
  }

  async function fetchScopeVariables(trigger = '', sourceKind = null) {
    try {
      const data = await graphql(SCOPE_VARS_QUERY, { trigger: trigger || '', sourceKind: sourceKind || null })
      scopeVariables.value = data?.scopeVariables || []
    } catch {
      scopeVariables.value = []
    }
  }

  async function validate() {
    try {
      const input = {
        id: sfxId.value || generateSfxId(draft.name) || 'sfx-draft',
        name: draft.name || 'Draft',
        trigger: draft.trigger,
        sourceKind: draft.source_kind || null,
        placement: draft.placement || null,
        conditions: draft.conditions || [],
        effects: draft.effects || [],
        duration: draft.duration,
      }
      const data = await graphql(VALIDATE_QUERY, { input })
      validationWarnings.value = data?.validateSfx || []
    } catch {
      validationWarnings.value = []
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
          conditions: draft.conditions, effects: draft.effects, duration: draft.duration,
        },
      })
      if (!result) { errorMsg.value = apiError.value || 'Save failed'; return false }
      patchData('sfxs', sfxId.value, {
        name: draft.name, trigger: draft.trigger, description: draft.description,
        source_kind: draft.source_kind, placement: draft.placement,
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
        id, name: draft.name.trim(), trigger: draft.trigger, description: draft.description,
        source_kind: draft.source_kind, placement: draft.placement,
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

  // One-time side effects (Rule 2): watchers are registered once against the
  // module-level draft; both panels share the same reactive state. Sync flush
  // lets `open()` suppress the initial assignment via `_suppressEdits`.
  if (!_watchersSetup) {
    _watchersSetup = true
    watch(() => [draft.trigger, draft.source_kind], ([t, sk]) => {
      if (_suppressEdits) return
      fetchScopeVariables(t || '', sk || null)
    }, { flush: 'sync' })
    watch(() => [draft.trigger, draft.source_kind, draft.conditions, draft.effects], () => {
      if (_suppressEdits) return
      clearTimeout(_validationTimer)
      _validationTimer = setTimeout(validate, 400)
    }, { deep: true, flush: 'sync' })
    watch(
      () => [draft.name, draft.description, draft.trigger, draft.source_kind, draft.placement, draft.conditions, draft.duration, draft.effects],
      () => {
        if (_suppressEdits) return
        if (!sfxId.value) return
        savedAt.value = null
        clearTimeout(_saveTimer)
        _saveTimer = setTimeout(save, 700)
      },
      { deep: true, flush: 'sync' },
    )
  }

  return {
    sfxId, draft, saving, errorMsg, successMsg, savedAt, validationWarnings, scopeVariables,
    open, reset, save, create, remove, validate, fetchScopeVariables,
  }
}
