<template>
  <div>
    <div class="panel-top">
      <span class="entity-type-badge" :class="'type-' + (form.type || '')">{{ form.type }}</span>
    </div>
    <GmEntityForm
      v-model="form"
      :entity-id="entityId"
    />
    <div v-if="form.type === 'LOCATION' || form.type === 'GMC'" class="canvas-open-row">
      <button class="section-btn" @click="openCanvas">🗺 Open in Canvas</button>
      <button v-if="form.type === 'LOCATION'" class="section-btn" @click="emit('go-to-location')">📍 Go to this location</button>
    </div>
    <div class="image-gallery">
      <div class="gallery-header">
        <h4>Images</h4>
        <div class="gallery-actions">
          <label class="upload-btn">
            📤 Upload
            <input type="file" accept="image/*" @change="onUpload" hidden />
          </label>
          <button class="imagen-btn" :class="{ cancelling: imagenStatus.cancelling }" @click="onImagenClick">
            <span class="btn-label">{{ imagenStatus.label }}</span>
            <span v-if="imagenStatus.status" class="btn-status">{{ imagenStatus.status }}</span>
          </button>
        </div>
      </div>
      <div v-if="!entityImages.length" class="gallery-empty">No entity images yet — upload or generate one.</div>
      <div v-else class="gallery-grid entity-gallery-drop" :class="{ 'drag-over': dropTarget === '__entity__' }" @dragover.prevent="onEntityDragOver" @dragleave="onEntityDragLeave" @drop.prevent="onEntityDrop">
        <div
          v-for="img in entityImages"
          :key="img.id"
          class="gallery-item"
          draggable="true"
          @dragstart="onImageDragStart($event, img)"
          @touchstart="onImageTouchStart($event, img)"
          @touchmove="onImageTouchMove"
          @touchend="onImageTouchEnd"
          @click="openImage(img)"
        >
          <MediaImage :src="img.image_type === 'animated' ? img.path_animated : img.path_large" class="gallery-thumb" :alt="img.image_type" lazy />
          <span class="gallery-label">
            {{ img.image_type }} — {{ formatSize(img.size_bytes) }}
            <span v-if="img.universe_label" class="universe-badge">{{ img.universe_label }}</span>
            <span v-for="r in img.roles" :key="r" class="role-badge">{{ r }}</span>
          </span>
        </div>
      </div>
    </div>
    <div v-if="isOccupant" class="projections-section">
      <div class="gallery-header">
        <h4>Projections</h4>
      </div>
      <div v-if="!projections.length" class="gallery-empty">No projections yet.</div>
      <div v-else class="projection-list">
        <div v-for="p in projections" :key="p.id" class="projection-block">
          <div
            class="projection-row"
            :class="{ 'drag-over': dropTarget === p.id }"
            :data-projection-id="p.id"
            @dragover.prevent="onProjDragOver(p)"
            @dragleave="onProjDragLeave(p)"
            @drop.prevent="onProjDrop(p, $event)"
            @click="openProjectionEditor(p)"
          >
            <MediaImage v-if="projectionThumb(p)" :src="projectionThumb(p).image_type === 'animated' ? projectionThumb(p).path_animated : projectionThumb(p).path_large" class="proj-thumb" :alt="p.originUniverse" />
            <span v-else class="proj-thumb proj-thumb-empty">🖼</span>
            <span class="proj-name">{{ p.name || form?.name }}</span>
            <span class="proj-universe">{{ universeName(p.originUniverse) }}<template v-if="p.universe !== p.originUniverse"> → {{ universeName(p.universe) }}</template></span>
            <span class="proj-type" :class="{ active: p.id === currentProjection }">{{ p.transversalType.toLowerCase() }}<template v-if="p.id === currentProjection"> · active</template></span>
            <button class="proj-imagen" :class="{ cancelling: projectionGenBusy(p) }" :title="projectionGenBusy(p) ? 'Cancel generation' : 'Generate image for this body'" @click.stop="onImagenClick(p.id)">{{ projectionGenBusy(p) ? '✕' : '🖼' }}</button>
            <button class="proj-remove" @click.stop="removeProjection(p.id)" title="Remove projection">✕</button>
          </div>
          <div v-if="projectionImages(p).length" class="gallery-grid projection-gallery">
            <div
              v-for="img in projectionImages(p)"
              :key="img.id"
              class="gallery-item"
              draggable="true"
              @dragstart="onImageDragStart($event, img)"
              @touchstart="onImageTouchStart($event, img)"
              @touchmove="onImageTouchMove"
              @touchend="onImageTouchEnd"
              @click="openImage(img)"
            >
              <MediaImage :src="img.image_type === 'animated' ? img.path_animated : img.path_large" class="gallery-thumb" :alt="img.image_type" lazy />
              <span class="gallery-label">
                {{ img.image_type }} — {{ formatSize(img.size_bytes) }}
                <span v-for="r in img.roles" :key="r" class="role-badge">{{ r }}</span>
              </span>
            </div>
          </div>
        </div>
      </div>
      <div class="projection-add">
        <GmLocationPicker v-model="newProjLocationId" placeholder="Search location…" class="proj-picker" @select="onLocationSelect" />
        <select v-model="newProjType" class="proj-type-select">
          <option value="NATIVE">native</option>
          <option value="CONSCIOUSNESS">consciousness</option>
          <option value="INAPPOSITE">inapposite</option>
        </select>
        <button class="section-btn proj-add-btn" @click="addProjectionLocal">+ Add</button>
      </div>
    </div>
    <div v-if="form.type === 'LOCATION'" class="transversal-links">
      <div class="gallery-header">
        <h4>Transversal Links</h4>
      </div>
      <div v-if="!transversalLinks.length" class="gallery-empty">No transversal links yet.</div>
      <div v-else class="transversal-list">
        <div v-for="link in transversalLinks" :key="link._key" class="transversal-row">
          <span class="transversal-name">{{ link.name }}</span>
          <button class="transversal-effects" :class="{ has: (link.effects || []).length }" title="Edit portal effects" @click="openPortalConfig(link)">
            ⚙{{ (link.effects || []).length || '' }}
          </button>
          <button class="transversal-toggle" :class="link.transversal_type || 'inapposite'" @click="toggleLinkType(link)">
            {{ link.transversal_type || 'inapposite' }}
          </button>
        </div>
      </div>
      <div class="transversal-add">
        <GmLocationPicker v-model="newTransversalLocationId" placeholder="Add link to location…" class="proj-picker" @select="onTransversalLocationSelect" />
        <button class="section-btn proj-add-btn" @click="createTransversalLinkLocal">+ Add</button>
      </div>
    </div>
    <div v-if="form.type === 'LOCATION' || form.type === 'UNIVERSE'" class="zones-section">
      <div class="gallery-header">
        <h4>Zones</h4>
      </div>
      <div v-if="!zones.length" class="gallery-empty">No sub-locations yet.</div>
      <div v-else class="zones-list">
        <div v-for="z in zones" :key="z.id" class="zone-row">
          <span class="zone-name">{{ z.name }}</span>
        </div>
      </div>
      <div class="zones-add">
        <input v-model="newZoneName" class="zone-input" placeholder="New sub-location name…" @keyup.enter="createZone" />
        <button class="section-btn zone-add-btn" :disabled="!newZoneName.trim() || creatingZone" @click="createZone">
          {{ creatingZone ? '…' : '+ Add' }}
        </button>
      </div>
    </div>
    <div v-if="form.type === 'UNIVERSE'" class="section-buttons">
      <button class="section-btn" @click="openLoraConfig">🖼 LoRA Configuration</button>
      <button class="section-btn" @click="openLifePaths">📋 Life Paths <span v-if="lifePaths.length" class="section-count">{{ lifePaths.length }}</span></button>
    </div>
    <div class="danger-zone">
      <h4>Danger Zone</h4>
      <div class="danger-actions">
        <DangerButton
          label="Delete"
          @confirm="onDeleteConfirmed"
        />
        <DangerButton
          v-if="form.type === 'LOCATION'"
          label="Prune"
          @confirm="onPruneConfirmed"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useEntityCrud } from '@/composables/useEntityCrud.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { useLifePaths } from '@/composables/useLifePaths.js'
import { useUniverseNames } from '@/composables/useUniverseNames.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import { useTransversalLinks } from '@/composables/useTransversalLinks.js'
import GmEntityForm from '@/components/gm/GmEntityForm.vue'
import ImageViewer from '@/components/gm/ImageViewer.vue'
import GmLoRAConfigPanel from '@/components/gm/GmLoRAConfigPanel.vue'
import GmLifePathsPanel from '@/components/gm/GmLifePathsPanel.vue'
import GmProjectionEditPanel from '@/components/gm/GmProjectionEditPanel.vue'
import GmPortalConfigPanel from '@/components/gm/GmPortalConfigPanel.vue'
import GmLocationPicker from '@/components/gm/GmLocationPicker.vue'
import DangerButton from '@/components/gm/DangerButton.vue'
import MediaImage from '@/components/MediaImage.vue'

const panel = usePanel()
const bus = usePanelBus()
const { graphql } = useApi()

// ── Composables: shared state with GmPanel ──────────
const { form, deleteEntity, uploadBgImage, onImagen: doImagen, onCancel: doCancel, imagenJob, projections, currentProjection, addProjection, removeProjection } = useEntityCrud()
const { traitNameMap } = useTraitsConfig()
const { paths: lifePaths, loading: loadingLifepaths, fetchLifePaths } = useLifePaths()
const { name: universeName, load: loadUniverseNames } = useUniverseNames()
loadUniverseNames()

const isOccupant = computed(() => ['CHARACTER', 'GMC', 'ASSET'].includes(form.value?.type))
const newProjLocationId = ref('')
const newProjLocation = ref(null)
const newProjType = ref('NATIVE')

function onLocationSelect(loc) {
  newProjLocation.value = loc
}

async function addProjectionLocal() {
  const loc = newProjLocation.value
  if (!loc || !loc.universe) return
  await addProjection(loc.universe, newProjType.value, loc.id)
  newProjLocationId.value = ''
  newProjLocation.value = null
}

// ── Image → projection drag-and-drop (HTML5 + touch longpress) ──
const dropTarget = ref(null)  // projection id, or '__entity__' for the entity gallery
const touchImageDrag = ref(null)

// Entity-level vs projection-scoped images (ownership is ``projection_id``).
const entityImages = computed(() => images.value.filter(i => !i.projection_id))
function projectionImages(p) { return images.value.filter(i => i.projection_id === p.id) }
function projectionThumb(p) {
  const list = projectionImages(p)
  return list.find(i => (i.roles || []).includes('sheet'))
    || list.find(i => (i.roles || []).includes('background'))
    || list[0] || null
}

async function assignImage(imageId, projectionId) {
  if (!imageId) return
  try {
    await fetch(`/api/v1/imagen/${imageId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ projection_id: projectionId || null }),
    })
    await loadImages()
  } catch (e) {
    console.error('assignImage:', e)
  }
}

async function onUpload(e) {
  await uploadBgImage(e)
  await loadImages()
  e.target.value = ''
}

function onImageDragStart(e, img) {
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('text/plain', JSON.stringify({ id: img.id, path: img.path_animated || img.path_large }))
}

function onProjDragOver(p) { dropTarget.value = p.id }
function onProjDragLeave(p) { if (dropTarget.value === p.id) dropTarget.value = null }
function onProjDrop(p, e) {
  dropTarget.value = null
  const raw = e.dataTransfer.getData('text/plain')
  if (!raw) return
  let payload
  try { payload = JSON.parse(raw) } catch { payload = { id: raw } }
  if (payload.id) assignImage(payload.id, p.id)
}

function onEntityDragOver() { dropTarget.value = '__entity__' }
function onEntityDragLeave() { if (dropTarget.value === '__entity__') dropTarget.value = null }
function onEntityDrop(e) {
  dropTarget.value = null
  const raw = e.dataTransfer.getData('text/plain')
  if (!raw) return
  let payload
  try { payload = JSON.parse(raw) } catch { payload = { id: raw } }
  if (payload.id) assignImage(payload.id, null)
}

function onImageTouchStart(e, img) {
  const touch = e.touches[0]
  const path = img.path_animated || img.path_large
  touchImageDrag.value = { id: img.id, path, sx: touch.clientX, sy: touch.clientY, engaged: false, ghost: null }
  touchImageDrag.value._timer = setTimeout(() => {
    if (!touchImageDrag.value) return
    touchImageDrag.value.engaged = true
    const ghost = document.createElement('img')
    ghost.src = touchImageDrag.value.path
    ghost.style.cssText = 'position:fixed;z-index:100;pointer-events:none;opacity:0.8;width:44px;height:44px;object-fit:cover;border-radius:4px'
    ghost.style.left = (touch.clientX - 22) + 'px'
    ghost.style.top = (touch.clientY - 22) + 'px'
    document.body.appendChild(ghost)
    touchImageDrag.value.ghost = ghost
  }, 400)
}

function onImageTouchMove(e) {
  if (!touchImageDrag.value) return
  if (!touchImageDrag.value.engaged) {
    const t = e.touches[0]
    if (Math.abs(t.clientX - touchImageDrag.value.sx) > 5 || Math.abs(t.clientY - touchImageDrag.value.sy) > 5) {
      clearTimeout(touchImageDrag.value._timer)
      touchImageDrag.value.ghost?.remove()
      touchImageDrag.value = null
    }
    return
  }
  const t = e.touches[0]
  const g = touchImageDrag.value.ghost
  if (g) { g.style.left = (t.clientX - 22) + 'px'; g.style.top = (t.clientY - 22) + 'px' }
  const target = document.elementFromPoint(t.clientX, t.clientY)
  if (target?.closest('.entity-gallery-drop')) dropTarget.value = '__entity__'
  else {
    const row = target?.closest('.projection-row')
    dropTarget.value = row ? (row.dataset.projectionId || null) : null
  }
}

function onImageTouchEnd(e) {
  if (!touchImageDrag.value) return
  clearTimeout(touchImageDrag.value._timer)
  if (touchImageDrag.value.engaged) {
    const t = e.changedTouches[0]
    const target = document.elementFromPoint(t.clientX, t.clientY)
    const id = touchImageDrag.value.id
    if (target?.closest('.entity-gallery-drop')) {
      if (id) assignImage(id, null)
    } else {
      const row = target?.closest('.projection-row')
      const projectionId = row?.dataset.projectionId
      if (projectionId && id) assignImage(id, projectionId)
    }
    touchImageDrag.value.ghost?.remove()
  }
  dropTarget.value = null
  touchImageDrag.value = null
}

const props = defineProps({
  entityId: { type: String, default: null },
})

const emit = defineEmits(['switch-to-sheet', 'image-open', 'go-to-location'])

// ── Sub-panel openers ───────────────────────────────
function openLoraConfig() {
  panel.open({
    component: GmLoRAConfigPanel,
    title: 'LoRA Configuration',
    props: { loraConfigJson: form.value.lora_config || '{}' },
    listeners: {
      'update:loraConfig': (json) => { form.value = { ...form.value, lora_config: json } },
    },
  })
}

function openLifePaths() {
  const currentUniverse = form.value?.current_universe || props.entityId
  panel.open({
    component: GmLifePathsPanel,
    title: 'Life Paths',
    props: { universe: currentUniverse },
  })
}

function openCanvas() {
  if (!props.entityId) return
  const type = form.value?.type
  if (type === 'LOCATION') {
    bus.emit('canvas:open-full', { mode: 'location', entityId: props.entityId, scope: 'focus' })
  } else if (type === 'GMC') {
    bus.emit('canvas:open-full', { mode: 'gmc-web', entityId: props.entityId })
  }
}

function openProjectionEditor(p) {
  panel.open({
    component: GmProjectionEditPanel,
    title: `Projection: ${p.originUniverse || p.universe}`,
    props: { projection: p },
  })
}

// Load life paths when editing a universe entity
watch(() => [props.entityId, form.value?.type], ([id, type]) => {
  if (id && type === 'UNIVERSE') fetchLifePaths(form.value.current_universe || props.entityId)
}, { immediate: true })

// ── Transversal links (location entities) ───────────
const transversalLinks = ref([])
const { toggleTransversalType, createTransversalLink } = useTransversalLinks()
const newTransversalLocationId = ref('')
const newTransversalLocation = ref(null)

async function loadTransversalLinks() {
  transversalLinks.value = []
  if (!props.entityId) return
  try {
    const r = await fetch(`/api/v1/locations/${props.entityId}/navigate`)
    if (r.ok) {
      const nav = await r.json()
      transversalLinks.value = nav.transversal || []
    }
  } catch {}
}

function onTransversalLocationSelect(loc) {
  newTransversalLocation.value = loc
}

async function createTransversalLinkLocal() {
  const loc = newTransversalLocation.value
  if (!loc || !loc.id) return
  await createTransversalLink(props.entityId, loc.id)
  newTransversalLocationId.value = ''
  newTransversalLocation.value = null
  await loadTransversalLinks()
}

async function toggleLinkType(link) {
  const next = await toggleTransversalType(props.entityId, link._key, link.transversal_type)
  link.transversal_type = next
}

function openPortalConfig(link) {
  panel.open({
    component: GmPortalConfigPanel,
    title: `Portal → ${link.name}`,
    props: { fromId: props.entityId, link, universe: form.value?.current_universe || '' },
  })
}

watch(() => [props.entityId, form.value?.type], ([id, type]) => {
  if (id && type === 'LOCATION') loadTransversalLinks()
}, { immediate: true })

// ── Zones (sub-locations) ───────────────────────────
const zones = ref([])
const newZoneName = ref('')
const creatingZone = ref(false)

async function loadZones() {
  zones.value = []
  if (!props.entityId) return
  try {
    if (form.value.type === 'LOCATION') {
      const r = await fetch(`/api/v1/locations/${props.entityId}/navigate`)
      if (r.ok) {
        const nav = await r.json()
        zones.value = (nav.children || []).map(c => ({ id: c._key || c.id, name: c.name }))
      }
    } else if (form.value.type === 'UNIVERSE') {
      const r = await fetch('/api/v1/locations/tree')
      if (r.ok) {
        const tree = await r.json()
        const uni = tree.find(n => n.id === props.entityId)
        zones.value = (uni?.children || []).map(c => ({ id: c.id, name: c.name }))
      }
    }
  } catch {}
}

async function createZone() {
  const name = newZoneName.value.trim()
  if (!name || creatingZone.value) return
  creatingZone.value = true
  try {
    const data = await graphql(
      `mutation($input: CreateEntityInput!) { createEntity(input: $input) { id } }`,
      { input: { name, type: 'LOCATION', universe: form.value.current_universe, location: null, razmerit: 0 } },
    )
    const newId = data?.createEntity?.id
    if (!newId) return
    if (form.value.type === 'LOCATION') {
      await fetch(`/api/v1/locations/${newId}/edges/${props.entityId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'super' }),
      })
    }
    newZoneName.value = ''
    await loadZones()
    bus.emit('locations-changed')
  } catch (e) {
    console.error('[zones] create failed', e)
  } finally {
    creatingZone.value = false
  }
}

watch(() => [props.entityId, form.value?.type], ([id, type]) => {
  if (id && (type === 'LOCATION' || type === 'UNIVERSE')) loadZones()
}, { immediate: true })

// ── Imagen ──────────────────────────────────────────
const localImagenJob = ref(null)
let _jobPollTimer = null

async function pollOwnJob() {
  if (!props.entityId) return
  try {
    const r = await fetch('/api/v1/imagen/jobs')
    if (r.ok) {
      const jobs = (await r.json()).jobs || {}
      localImagenJob.value = jobs[props.entityId] || null
    }
  } catch {}
}

const imagenStatus = computed(() => {
  const j = localImagenJob.value || imagenJob.value
  if (!j) return { label: '🖼 Imagen', status: '', cancelling: false }
  if (j.status === 'failed') return { label: '🖼 Imagen', status: '!', cancelling: false }
  return { label: 'Cancel', status: '✕', cancelling: true }
})

const genTarget = ref(null)  // projection id (or '' for entity) of the active generation

function onImagenClick(projectionId = '') {
  if (imagenStatus.value.cancelling) {
    doCancel()
    genTarget.value = null
    return
  }
  genTarget.value = projectionId
  doImagen(projectionId)
}

function projectionGenBusy(p) {
  return genTarget.value === p.id && imagenStatus.value.cancelling
}

// Refresh gallery when a job completes
watch(localImagenJob, (now, prev) => {
  if (prev && !now) { loadImages(); genTarget.value = null }
})

// ── Delete / prune (two-click confirm handled by DangerButton) ──
async function onDeleteConfirmed() {
  await deleteEntity(props.entityId)
  panel.close()
}

async function onPruneConfirmed() {
  await deleteEntity(props.entityId, true)
  panel.close()
}

function formatSize(bytes) {
  if (!bytes || bytes === 0) return ''
  return bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`
}

// ── Image gallery (panel-specific) ──────────────────
const openedImageId = ref(null)

function openImage(img) {
  if (openedImageId.value === img.id) {
    panel.closeChild(); openedImageId.value = null
    return
  }
  openedImageId.value = img.id
  panel.open({
    component: ImageViewer,
    title: img.id,
    props: { src: img.path_animated || img.path_large, animatedSrc: img.path_animated, alt: img.image_type + ' — ' + img.width + '×' + img.height, entityId: props.entityId, imageId: img.id, imageType: img.image_type, roles: img.roles || [], sizeBytes: img.size_bytes },
    listeners: {
      'close': () => { openedImageId.value = null },
    },
  })
}

const images = ref([])

async function loadImages() {
  if (!props.entityId) return
  try {
    const r = await fetch(`/api/v1/imagen/${props.entityId}`)
    if (r.ok) { const d = await r.json(); images.value = d.images || [] }
  } catch {}
}

watch(() => props.entityId, loadImages, { immediate: true })
onMounted(() => { pollOwnJob(); _jobPollTimer = setInterval(pollOwnJob, 2000) })
let offLifepathSaved = null
onMounted(() => {
  offLifepathSaved = bus.on('lifepath-saved', () => {
    if (form.value?.type === 'UNIVERSE') fetchLifePaths(form.value.current_universe || props.entityId)
  })
})
onUnmounted(() => { clearInterval(_jobPollTimer); if (offLifepathSaved) offLifepathSaved() })
defineExpose({ refresh: loadImages })
</script>

<style scoped>
.imagen-btn { background: #8b5cf6; color: #fff; font-size: 11px; padding: 0; border-radius: 4px; border: none; cursor: pointer; display: inline-flex; overflow: hidden; }
.imagen-btn.cancelling { background: #dc2626; }
.imagen-btn .btn-label { padding: 4px 8px; }
.imagen-btn .btn-status { padding: 4px 8px; background: rgba(0,0,0,0.25); font-weight: 600; }

.panel-top { display: flex; justify-content: flex-end; margin-bottom: 8px; }
.danger-zone {
  margin-top: 12px; padding: 10px;
  border: 1px solid rgba(220,64,64,0.25); border-radius: 6px;
  background: rgba(220,64,64,0.06);
}
.danger-zone h4 {
  font-size: 10px; color: #e06060; text-transform: uppercase; letter-spacing: 1px;
  margin: 0 0 8px 0;
}
.danger-actions { display: flex; gap: 6px; }
.danger-actions :deep(.danger-button) { flex: 1; width: auto; }

.image-gallery { margin-top: 12px; }
.gallery-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.gallery-header h4 { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin: 0; }
.gallery-actions { display: flex; gap: 6px; align-items: center; }
.upload-btn {
  font-size: 11px; padding: 4px 8px; cursor: pointer; display: inline-flex; align-items: center;
  background: var(--accent-dim); color: var(--text); border-radius: 4px; border: none;
}
.gallery-empty { font-size: 10px; color: var(--text-dim); padding: 12px 0; text-align: center; }
.gallery-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 6px; }
.gallery-item { display: block; border: 1px solid rgba(255,255,255,0.08); border-radius: 4px; overflow: hidden; cursor: pointer; }
.gallery-item img { width: 100%; height: auto; display: block; }
.gallery-thumb, .gallery-thumb-video { width: 100%; height: auto; display: block; }
.gallery-label { display: block; font-size: 9px; color: var(--text-dim); text-align: center; padding: 2px 4px; background: rgba(0,0,0,0.3); }
.universe-badge { display: inline-block; font-size: 7px; background: rgba(139,92,246,0.3); color: #c4b5fd; padding: 0 3px; border-radius: 2px; margin-left: 3px; }
.role-badge { display: inline-block; font-size: 7px; background: rgba(245,158,11,0.3); color: #fcd34d; padding: 0 3px; border-radius: 2px; margin-left: 2px; text-transform: uppercase; }

.section-buttons {
  margin-top: 12px; display: flex; gap: 6px;
}
.canvas-open-row { margin-top: 12px; display: flex; gap: 6px; }
.section-btn {
  flex: 1; padding: 8px 12px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.08);
  background: rgba(255,255,255,0.03); color: var(--text); cursor: pointer;
  font-size: 12px; text-align: center;
  transition: border-color 0.15s;
}
.section-btn:hover { border-color: rgba(255,255,255,0.15); background: rgba(255,255,255,0.05); }
.section-count { font-size: 10px; color: var(--text-dim); margin-left: 4px; }

.projections-section { margin-top: 12px; }
.projection-list { display: flex; flex-direction: column; gap: 8px; }
.projection-block { border: 1px solid rgba(255,255,255,0.05); border-radius: 6px; padding: 4px; }
.projection-row { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border: 1px solid rgba(255,255,255,0.08); border-radius: 4px; background: rgba(255,255,255,0.02); }
.proj-name { flex: 1; font-size: 12px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.proj-universe { font-size: 11px; color: var(--text-dim); }
.proj-type { font-size: 10px; text-transform: uppercase; color: var(--text-dim); padding: 1px 6px; border-radius: 3px; background: rgba(255,255,255,0.04); }
.proj-type.active { color: #93c5fd; background: rgba(64,136,212,0.18); }
.proj-remove { background: transparent; border: none; color: var(--text-dim); cursor: pointer; font-size: 12px; }
.proj-remove:hover { color: #e06060; }
.proj-imagen { background: transparent; border: none; color: var(--text-dim); cursor: pointer; font-size: 12px; }
.proj-imagen:hover { color: var(--accent); }
.proj-imagen.cancelling { color: #dc2626; }
.projection-add { display: flex; gap: 6px; margin-top: 8px; }
.proj-input { flex: 1; padding: 6px 8px; border: 1px solid rgba(255,255,255,0.08); border-radius: 4px; background: var(--bg-input); color: var(--text); font-size: 12px; }
.proj-type-select { padding: 6px; border: 1px solid rgba(255,255,255,0.08); border-radius: 4px; background: var(--bg-input); color: var(--text); font-size: 12px; }
.proj-add-btn { flex: 0 0 auto; padding: 6px 10px; }
.proj-picker { flex: 1; min-width: 0; }
.proj-thumb { width: 32px; height: 32px; object-fit: cover; border-radius: 4px; border: 1px solid rgba(255,255,255,0.12); flex: 0 0 auto; }
.proj-thumb-empty { display: flex; align-items: center; justify-content: center; font-size: 14px; color: var(--text-dim); background: rgba(255,255,255,0.04); }
.projection-row.drag-over { border-color: var(--accent); background: rgba(64,136,212,0.12); }
.projection-gallery { margin-top: 4px; padding: 4px; border-top: 1px dashed rgba(255,255,255,0.08); }
.entity-gallery-drop.drag-over { outline: 2px dashed var(--accent); outline-offset: 2px; }
.transversal-links { margin-top: 12px; }
.transversal-list { display: flex; flex-direction: column; gap: 4px; }
.transversal-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 6px 8px; border: 1px solid rgba(255,255,255,0.08); border-radius: 4px; background: rgba(255,255,255,0.02); }
.transversal-name { font-size: 12px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.transversal-toggle { font-size: 10px; padding: 2px 8px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.1); cursor: pointer; }
.transversal-toggle.inapposite { background: rgba(139,92,246,0.18); color: #c4b5fd; }
.transversal-toggle.consciousness { background: rgba(245,158,11,0.18); color: #fcd34d; }
.transversal-effects { background: transparent; border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; color: var(--text-dim); cursor: pointer; font-size: 10px; padding: 2px 7px; }
.transversal-effects.has { color: var(--accent); border-color: var(--accent-dim); }
.transversal-effects:hover { color: var(--accent); border-color: var(--accent); }
.transversal-add { display: flex; gap: 6px; margin-top: 8px; }
.zones-section { margin-top: 12px; }
.zones-list { display: flex; flex-direction: column; gap: 4px; }
.zone-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 6px 8px; border: 1px solid rgba(255,255,255,0.08); border-radius: 4px; background: rgba(255,255,255,0.02); }
.zone-name { font-size: 12px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.zones-add { display: flex; gap: 6px; margin-top: 8px; }
.zone-input { flex: 1; padding: 6px 8px; border: 1px solid rgba(255,255,255,0.08); border-radius: 4px; background: var(--bg-input); color: var(--text); font-size: 12px; }
.zone-add-btn { flex: 0 0 auto; padding: 6px 10px; }
</style>
