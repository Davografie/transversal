import { ref, computed, watch } from 'vue'
import { useApi } from './useApi.js'

// ── Module-level singleton state ─────────────────────
const entities = ref([])
const selected = ref(null)
const selectedId = ref(null)
const editing = ref(false)
const creating = ref(false)
const saving = ref(false)
const form = ref({})
const projections = ref([])
const currentProjection = ref(null)

// ── Imagen job state ─────────────────────────────────
const jobStatuses = ref({})  // {entity_id: {type, status, percent, message}}

// ── Watcher guard: only set up once ──────────────────
let _watchersSetup = false

export function useEntityCrud() {
  const { graphql, imagenEntity } = useApi()

  // ── Queries ────────────────────────────────────────
  const ENTITY_QUERY = `query($id: ID!) {
    entity(id: $id) {
      id type name razmerit currentUniverse currentLocation currentProjection
      hidden unpublished supportEligible starterLocation loraConfig
      projections {
        id originUniverse universe name backgroundImage currentLocation transversalType
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
      }
      return alreadyEditing
    }
    return false
  }

  // ── Mutations ──────────────────────────────────────
  // ⚠ Must update selected.value directly — must NOT call selectEntity().
  async function saveEntity() {
    saving.value = true
    const result = await graphql(
      `mutation($input: UpdateEntityInput!) {
        updateEntity(input: $input) {
          id name razmerit currentUniverse currentLocation hidden unpublished supportEligible starterLocation loraConfig
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
    await graphql(
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
    saving.value = false
    creating.value = false
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
          id originUniverse universe name currentLocation transversalType
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

  // ── Image upload ───────────────────────────────────
  async function uploadBgImage(e) {
    const file = e.target?.files?.[0]
    if (!file || !selected.value?.id) return
    const fd = new FormData()
    fd.append('file', file)
    try {
      await fetch(
        `/api/v1/media/upload?entity_id=${encodeURIComponent(selected.value.id)}`,
        { method: 'POST', body: fd }
      )
      // The upload registers the image in entity_images; roles (background/
      // sheet/navdot) are assigned in the image viewer. No legacy field write.
    } catch (err) {
      console.error('uploadBgImage:', err)
    }
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

  // ── Auto-save watcher (guarded: only set up once) ──
  if (!_watchersSetup) {
    _watchersSetup = true
    let entitySaveTimer = null
    watch(
      () => form.value,
      () => {
        if (!editing.value || !selected.value) return
        clearTimeout(entitySaveTimer)
        entitySaveTimer = setTimeout(() => saveEntity(), 600)
      },
      { deep: true }
    )
  }

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
    removeProjection,
    uploadBgImage,
    // Imagen actions
    pollJobs,
    startJobPolling,
    stopJobPolling,
    onImagen,
    onCancel,
  }
}
