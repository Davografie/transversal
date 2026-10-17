import { ref, computed, watch } from 'vue'
import { useApi } from './useApi.js'

// ── Entity CRUD, one instance per editor ─────────────
// Every ref lives inside the factory. Entity *panels* each take their own
// instance, so two open panels (a detached one and the one behind it, say)
// cannot overwrite each other's form/selection — they used to share one
// module-level form, and opening a second entity renamed the first panel's
// Name field. useEntityCrud() below returns the shared instance for genuinely
// global state: the GM panel's entity list, the app prefetch, the create
// panel's saving flag, the projection editor's list patch.
export function createEntityCrud() {
  const { graphql, imagenEntity } = useApi()

  const entities = ref([])
  const selected = ref(null)
  const selectedId = ref(null)
  const editing = ref(false)
  const creating = ref(false)
  const saving = ref(false)
  const form = ref({})
  const projections = ref([])
  const currentProjection = ref(null)

  // ── Imagen job state ───────────────────────────────
  const jobStatuses = ref({})  // {entity_id: {type, status, percent, message}}

  // ── Queries ────────────────────────────────────────
  // `carriedLocations` and `carrier` are the two halves of an inner world: what
  // this entity carries, and who carries it. Read-only here — the entity panel
  // lists the first and names the second, and the Places tree shows neither
  // ([[B308]]). ⚠ No comments *inside* the query below: a GraphQL document has no
  // `//`, and one there is a syntax error that fails every panel silently.
  const ENTITY_QUERY = `query($id: ID!) {
    entity(id: $id) {
      id type name razmerit currentUniverse currentLocation currentProjection
      hidden unpublished supportEligible starterLocation loraConfig promptSteering namingTheme
      sfxIds
      agency { playerId playerName main }
      carriedLocations { id name currentUniverse }
      carrier { id name type }
      projections {
        id entityId originUniverse universe name backgroundImage currentLocation transversalType
      }
      traitSettings {
        id name dieType rating ratingType statement ego sfxIds traitsetName universe
      }
    }
  }`

  async function fetchEntities() {
    const data = await graphql(
      `query($type: EntityType) {
        entities(type: $type) {
          id type name razmerit currentUniverse currentLocation hidden unpublished supportEligible
        }
      }`,
      { type: null }
    )
    if (data?.entities) entities.value = data.entities
  }

  // ⚠ Must update selected.value directly — must NOT call selectEntity() here.
  // selectEntity() sets form.value (new object), which triggers the watcher,
  // which calls saveEntity() again → infinite re-open loop.
  async function selectEntity(e) {
    // Re-reading the entity we are already editing: flush the pending auto-save
    // first, or the read returns the pre-edit value and the form is rebuilt from
    // it — which is how a tick taken just before a tab switch got reverted.
    if (editing.value && selectedId.value === e.id) await flushPendingSave()
    const alreadyEditing = editing.value && selectedId.value === e.id
    const data = await graphql(ENTITY_QUERY, { id: e.id })
    if (data?.entity) {
      selected.value = data.entity
      projections.value = data.entity.projections || []
      currentProjection.value = data.entity.currentProjection || null
      selectedId.value = e.id
      editing.value = true
      form.value = {
        name: data.entity.name,
        type: data.entity.type,
        current_universe: data.entity.currentUniverse,
        current_location: data.entity.currentLocation || '',
        razmerit: data.entity.razmerit,
        overlay: data.entity.overlay || null,
        hidden: data.entity.hidden,
        unpublished: data.entity.unpublished ?? false,
        support_eligible: data.entity.supportEligible ?? false,
        starter_location: data.entity.starterLocation ?? false,
        lora_config: data.entity.loraConfig || '{}',
        prompt_steering: data.entity.promptSteering || '',
        // B82: universe-only, and `''` genuinely means "the world default", so it
        // round-trips as an empty string rather than being dropped.
        naming_theme: data.entity.namingTheme || '',
      }
      return alreadyEditing
    }
    return false
  }

  // ── Mutations ──────────────────────────────────────
  // ⚠ Must update selected.value directly — must NOT call selectEntity().
  // The in-flight save is tracked so a re-read can wait for the newest intent to
  // land: a panel that re-reads *while* a save is on the wire would otherwise read
  // the pre-edit value back and save it (see `flushPendingSave`). The body lives
  // in `doSaveEntity` so `saveEntity` keeps its name and behaviour for callers.
  let saveInFlight = null
  async function saveEntity() {
    const run = doSaveEntity()
    saveInFlight = run
    try {
      return await run
    } finally {
      if (saveInFlight === run) saveInFlight = null
    }
  }

  async function doSaveEntity() {
    saving.value = true
    const result = await graphql(
      `mutation($input: UpdateEntityInput!) {
        updateEntity(input: $input) {
          id name razmerit currentUniverse currentLocation hidden unpublished supportEligible starterLocation loraConfig promptSteering namingTheme
        }
      }`,
      {
        input: {
          id: selected.value.id,
          name: form.value.name,
          razmerit: form.value.razmerit,
          currentUniverse: form.value.current_universe,
          currentLocation: form.value.current_location || null,
          hidden: form.value.hidden,
          unpublished: form.value.unpublished,
          supportEligible: form.value.support_eligible,
          overlay: form.value.overlay,
          starterLocation: form.value.starter_location,
          loraConfig: form.value.lora_config,
          promptSteering: form.value.prompt_steering,
          namingTheme: form.value.naming_theme || '',
        },
      }
    )
    if (result?.updateEntity) {
      const ue = result.updateEntity
      if (selected.value) {
        selected.value.name = ue.name
        selected.value.razmerit = ue.razmerit
        selected.value.currentUniverse = ue.currentUniverse
        selected.value.currentLocation = ue.currentLocation
        selected.value.hidden = ue.hidden
        selected.value.unpublished = ue.unpublished
        selected.value.supportEligible = ue.supportEligible
        selected.value.starterLocation = ue.starterLocation
        selected.value.namingTheme = ue.namingTheme || ''
      }
    }
    saving.value = false
    await fetchEntities()
  }

  async function deleteEntity(id, rmtree = false) {
    const isLoc = selected.value?.type === 'LOCATION'
    await graphql(
      `mutation($id: ID!, $rmtree: Boolean!) { deleteEntity(id: $id, rmtree: $rmtree) }`,
      { id, rmtree }
    )
    selected.value = null
    selectedId.value = null
    editing.value = false
    // Caller handles location tree refresh and close
    return { wasLocation: isLoc }
  }

  async function createEntity(formData) {
    saving.value = true
    try {
      const result = await graphql(
        `mutation($input: CreateEntityInput!) {
          createEntity(input: $input) { id name type razmerit currentUniverse currentLocation }
        }`,
        {
          input: {
            name: formData.name,
            type: formData.type,
            universe: formData.universe,
            location: formData.location || null,
            razmerit: formData.razmerit || 0,
          },
        }
      )
      // A location's parent is an **edge**, not a field. `create_entity` stores
      // the denormalized `current_location` and writes no `super` edge, so a zone
      // created under a parent would never appear in the tree (nor get the
      // parent's zone / the child's nav-dot defaults, which the edge endpoint
      // seeds). The entity panel's Zones section does these same two steps by
      // hand; this is the one place the tree's create rows land, so the edge
      // belongs here.
      const created = result?.createEntity
      if (created?.id && formData.type === 'LOCATION' && formData.location) {
        await fetch(`/api/v1/locations/${created.id}/edges/${formData.location}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ type: 'super' }),
        })
      }
    } finally {
      // The edge write is a second thing that can throw; the create panel's
      // spinner must not survive either failure.
      saving.value = false
      creating.value = false
    }
    await fetchEntities()
  }

  // ── Projections ────────────────────────────────────
  async function addProjection(universe, type = 'NATIVE', location = null) {
    const result = await graphql(
      `mutation($entityId: ID!, $universe: String!, $type: TransversalType!, $location: ID) {
        addProjection(entityId: $entityId, universe: $universe, type: $type, location: $location) {
          id currentProjection
          projections { id originUniverse universe name backgroundImage currentLocation transversalType }
        }
      }`,
      { entityId: selected.value.id, universe, type, location }
    )
    if (result?.addProjection) {
      projections.value = result.addProjection.projections || []
      currentProjection.value = result.addProjection.currentProjection || null
    }
    return result?.addProjection || null
  }

  async function updateProjection(projectionId, patch = {}) {
    const result = await graphql(
      `mutation($projectionId: ID!, $name: String, $currentLocation: ID, $transversalType: TransversalType) {
        updateProjection(projectionId: $projectionId, name: $name, currentLocation: $currentLocation, transversalType: $transversalType) {
          id entityId originUniverse universe name currentLocation transversalType
        }
      }`,
      {
        projectionId,
        name: patch.name ?? null,
        currentLocation: patch.currentLocation ?? null,
        transversalType: patch.transversalType ?? null,
      }
    )
    if (result?.updateProjection) {
      const p = result.updateProjection
      const idx = projections.value.findIndex((x) => x.id === p.id)
      if (idx >= 0) projections.value[idx] = p
    }
    return result?.updateProjection || null
  }

  // Send a body to a location, or make it the entity's current body in place
  // (`location` null). Travel, not a field edit: the service derives the body's
  // universe from the destination location, makes it the entity's current body,
  // and mirrors the entity's universe/location onto it — so a cross-universe
  // destination lands with the record consistent and the entity following.
  // `entityId` is the panel's own entity; it falls back to this instance's
  // selection when the projection was opened outside an entity panel.
  async function activateProjection(projectionId, location, entityId = null) {
    const id = entityId || selectedId.value
    if (!id) return null
    const result = await graphql(
      `mutation($entityId: ID!, $projectionId: ID!, $location: ID) {
        activateProjection(entityId: $entityId, projectionId: $projectionId, location: $location) {
          id currentProjection currentUniverse currentLocation
          projections { id entityId originUniverse universe name backgroundImage currentLocation transversalType }
        }
      }`,
      { entityId: id, projectionId, location: location || null }
    )
    const e = result?.activateProjection
    if (!e) return null
    projections.value = e.projections || []
    currentProjection.value = e.currentProjection || null
    if (selected.value) {
      selected.value.currentProjection = e.currentProjection
      selected.value.currentUniverse = e.currentUniverse
      selected.value.currentLocation = e.currentLocation
    }
    // The entity panel's form drives its own auto-save; leaving it on the old
    // location would write the travel back out on the next edit.
    if (form.value && selectedId.value === id) {
      form.value.current_universe = e.currentUniverse
      form.value.current_location = e.currentLocation || ''
    }
    // The updated projection, matching updateProjection's contract (the panel
    // reads the new universe off it; its own prop is a frozen spec snapshot).
    return (e.projections || []).find((x) => x.id === projectionId) || null
  }

  async function removeProjection(projectionId) {
    const result = await graphql(
      `mutation($projectionId: ID!) {
        removeProjection(projectionId: $projectionId) {
          id currentProjection
          projections { id originUniverse universe name backgroundImage currentLocation transversalType }
        }
      }`,
      { projectionId }
    )
    if (result?.removeProjection) {
      projections.value = result.removeProjection.projections || []
      currentProjection.value = result.removeProjection.currentProjection || null
    }
    return result?.removeProjection || null
  }

  // ── Imagen ─────────────────────────────────────────
  const imagenJob = computed(() => {
    const j = jobStatuses.value[selectedId.value]
    return (j && j.type === 'imagen') ? j : null
  })

  const animateJob = computed(() => {
    const j = jobStatuses.value[selectedId.value]
    return (j && j.type === 'animate') ? j : null
  })

  async function pollJobs() {
    try {
      const r = await fetch('/api/v1/imagen/jobs')
      if (r.ok) jobStatuses.value = (await r.json()).jobs || {}
    } catch {}
  }

  let _jobPollTimer = null
  function startJobPolling() {
    pollJobs()
    _jobPollTimer = setInterval(pollJobs, 2000)
  }
  function stopJobPolling() {
    clearInterval(_jobPollTimer)
    _jobPollTimer = null
  }

  async function onImagen(projectionId = '') {
    if (!selectedId.value || imagenJob.value) return
    jobStatuses.value = {
      ...jobStatuses.value,
      [selectedId.value]: { type: 'imagen', status: 'queued', queue_position: '⋯' },
    }
    try {
      await imagenEntity(selectedId.value, projectionId)
    } catch (e) {
      const s = { ...jobStatuses.value }
      delete s[selectedId.value]
      jobStatuses.value = s
      console.error('[useEntityCrud] imagen failed:', e)
    }
  }

  async function onCancel() {
    if (!selectedId.value) return
    try {
      await fetch(`/api/v1/imagen/${selectedId.value}/cancel`, { method: 'POST' })
    } catch (e) {
      console.error('[useEntityCrud] cancel failed:', e)
    }
  }

  // ── Auto-save watcher — one per instance, following this instance's form ──
  let entitySaveTimer = null

  /**
   * Let a debounced auto-save land *now*.
   *
   * The save is 600ms behind the form, and `selectEntity` rebuilds the whole form
   * from the database. A panel re-reads itself whenever it becomes the active tab
   * again (see `GmEntityEditPanel`), so an edit made just before a tab switch used
   * to be read back as it was **stored** and then written that way — silently
   * reverting it. Nothing was lost at the wire: the newer intent simply never
   * reached the database. Flushing here makes the read below include the edit.
   */
  async function flushPendingSave() {
    // A save already on the wire carries newer intent than the database shows.
    if (saveInFlight) await saveInFlight
    if (!entitySaveTimer) return
    clearTimeout(entitySaveTimer)
    entitySaveTimer = null
    if (editing.value && selected.value) await saveEntity()
  }

  watch(
    () => form.value,
    () => {
      if (!editing.value || !selected.value) return
      clearTimeout(entitySaveTimer)
      entitySaveTimer = setTimeout(() => saveEntity(), 600)
    },
    { deep: true }
  )

  return {
    // State
    entities,
    selected,
    selectedId,
    editing,
    creating,
    saving,
    form,
    projections,
    currentProjection,
    // Imagen
    jobStatuses,
    imagenJob,
    animateJob,
    // Queries
    fetchEntities,
    selectEntity,
    // Mutations
    saveEntity,
    deleteEntity,
    createEntity,
    addProjection,
    updateProjection,
    activateProjection,
    removeProjection,
    // Imagen actions
    pollJobs,
    startJobPolling,
    stopJobPolling,
    onImagen,
    onCancel,
  }
}

// ── The shared instance ──────────────────────────────
let _sharedCrud = null
export function useEntityCrud() {
  if (!_sharedCrud) _sharedCrud = createEntityCrud()
  return _sharedCrud
}
