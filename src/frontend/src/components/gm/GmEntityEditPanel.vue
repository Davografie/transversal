<template>
  <div>
    <GmEntityForm
      v-model="form"
      :entity-id="entityId"
      :allow-type-change="false"
    />
    <div v-if="form.type === 'LOCATION' || form.type === 'GMC'" class="canvas-open-row">
      <button class="section-btn" @click="openCanvas">🗺 Open in Canvas</button>
    </div>
    <div class="image-gallery">
      <div class="gallery-header">
        <h4>Images</h4>
        <div class="gallery-actions">
          <label class="upload-btn">
            📤 Upload
            <input type="file" accept="image/*" @change="uploadBgImage" hidden />
          </label>
          <button class="imagen-btn" :class="{ cancelling: imagenStatus.cancelling }" @click="onImagenClick">
            <span class="btn-label">{{ imagenStatus.label }}</span>
            <span v-if="imagenStatus.status" class="btn-status">{{ imagenStatus.status }}</span>
          </button>
        </div>
      </div>
      <div v-if="!images.length" class="gallery-empty">No images yet — upload or generate one.</div>
      <div v-else class="gallery-grid">
        <div
          v-for="img in images"
          :key="img.id"
          class="gallery-item"
          draggable="true"
          @dragstart="onImageDragStart($event, img)"
          @touchstart="onImageTouchStart($event, img)"
          @touchmove="onImageTouchMove"
          @touchend="onImageTouchEnd"
          @click="openImage(img)"
        >
          <video v-if="img.image_type === 'animated'" :src="img.path_animated" class="gallery-thumb-video" autoplay loop muted playsinline />
          <img v-else :src="img.path_large" :alt="img.image_type" loading="lazy" />
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
        <div
          v-for="p in projections"
          :key="p.id"
          class="projection-row"
          :class="{ 'drag-over': dropTarget === p.originUniverse }"
          :data-origin-universe="p.originUniverse"
          @dragover.prevent="onProjDragOver(p)"
          @dragleave="onProjDragLeave(p)"
          @drop.prevent="onProjDrop(p, $event)"
        >
          <img v-if="p.backgroundImage" :src="p.backgroundImage" class="proj-thumb" :alt="p.originUniverse" />
          <span v-else class="proj-thumb proj-thumb-empty">🖼</span>
          <span class="proj-name">{{ p.name || form?.name }}</span>
          <span class="proj-universe">{{ p.originUniverse }}<template v-if="p.universe !== p.originUniverse"> → {{ p.universe }}</template></span>
          <span class="proj-type" :class="{ active: p.id === currentProjection }">{{ p.transversalType.toLowerCase() }}<template v-if="p.id === currentProjection"> · active</template></span>
          <button class="proj-remove" @click="removeProjection(p.originUniverse)" title="Remove projection">✕</button>
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
import { useEntityCrud } from '@/composables/useEntityCrud.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import { useLifePaths } from '@/composables/useLifePaths.js'
import { usePanel } from '@/composables/usePanel.js'
import { usePanelBus } from '@/composables/usePanelBus.js'
import GmEntityForm from '@/components/gm/GmEntityForm.vue'
import ImageViewer from '@/components/gm/ImageViewer.vue'
import GmLoRAConfigPanel from '@/components/gm/GmLoRAConfigPanel.vue'
import GmLifePathsPanel from '@/components/gm/GmLifePathsPanel.vue'
import GmLocationPicker from '@/components/gm/GmLocationPicker.vue'
import RelationalCanvas from '@/components/canvas/RelationalCanvas.vue'
import DangerButton from '@/components/gm/DangerButton.vue'

const panel = usePanel()
const bus = usePanelBus()

// ── Composables: shared state with GmPanel ──────────
const { form, deleteEntity, uploadBgImage, onImagen: doImagen, onCancel: doCancel, imagenJob, projections, currentProjection, addProjection, updateProjection, removeProjection } = useEntityCrud()
const { traitNameMap } = useTraitsConfig()
const { paths: lifePaths, loading: loadingLifepaths, fetchLifePaths } = useLifePaths()

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
const dropTarget = ref(null)
const touchImageDrag = ref(null)

function onImageDragStart(e, img) {
  e.dataTransfer.effectAllowed = 'copy'
  e.dataTransfer.setData('text/plain', JSON.stringify({ path: img.path_large || img.path_animated }))
}

function onProjDragOver(p) { dropTarget.value = p.originUniverse }
function onProjDragLeave(p) { if (dropTarget.value === p.originUniverse) dropTarget.value = null }
function onProjDrop(p, e) {
  dropTarget.value = null
  const raw = e.dataTransfer.getData('text/plain')
  if (!raw) return
  let payload
  try { payload = JSON.parse(raw) } catch { payload = { path: raw } }
  if (payload.path) updateProjection(p.originUniverse, { backgroundImage: payload.path })
}

function onImageTouchStart(e, img) {
  const touch = e.touches[0]
  touchImageDrag.value = { path: img.path_large || img.path_animated, sx: touch.clientX, sy: touch.clientY, engaged: false, ghost: null }
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
  const row = target?.closest('.projection-row')
  dropTarget.value = row ? (row.dataset.originUniverse || null) : null
}

function onImageTouchEnd(e) {
  if (!touchImageDrag.value) return
  clearTimeout(touchImageDrag.value._timer)
  if (touchImageDrag.value.engaged) {
    const t = e.changedTouches[0]
    const target = document.elementFromPoint(t.clientX, t.clientY)
    const row = target?.closest('.projection-row')
    const universe = row?.dataset.originUniverse
    if (universe && touchImageDrag.value.path) updateProjection(universe, { backgroundImage: touchImageDrag.value.path })
    touchImageDrag.value.ghost?.remove()
  }
  dropTarget.value = null
  touchImageDrag.value = null
}

const props = defineProps({
  entityId: { type: String, default: null },
})

const emit = defineEmits(['switch-to-sheet', 'image-open'])

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
    panel.open({
      component: RelationalCanvas,
      title: 'Location Canvas',
      props: { locationId: props.entityId },
    })
  } else if (type === 'GMC') {
    panel.open({
      component: RelationalCanvas,
      title: 'GMC Relations',
      props: { initialGmcId: props.entityId },
    })
  }
}

// Load life paths when editing a universe entity
watch(() => [props.entityId, form.value?.type], ([id, type]) => {
  if (id && type === 'UNIVERSE') fetchLifePaths(form.value.current_universe || props.entityId)
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

function onImagenClick() {
  if (imagenStatus.value.cancelling) doCancel()
  else doImagen()
}

// Refresh gallery when a job completes
watch(localImagenJob, (now, prev) => {
  if (prev && !now) loadImages()
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

.danger-zone {
  margin-top: 12px; padding: 10px;
  border: 1px solid rgba(220,64,64,0.25); border-radius: 6px;
  background: rgba(220,64,64,0.06);
}
.danger-zone h4 {
  font-size: 10px; color: #e06060; text-transform: uppercase; letter-spacing: 1px;
  margin: 0 0 8px 0;
}
.danger-actions { display: flex; flex-direction: column; gap: 6px; }

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
.gallery-thumb-video { width: 100%; height: auto; display: block; }
.gallery-label { display: block; font-size: 9px; color: var(--text-dim); text-align: center; padding: 2px 4px; background: rgba(0,0,0,0.3); }
.universe-badge { display: inline-block; font-size: 7px; background: rgba(139,92,246,0.3); color: #c4b5fd; padding: 0 3px; border-radius: 2px; margin-left: 3px; }
.role-badge { display: inline-block; font-size: 7px; background: rgba(245,158,11,0.3); color: #fcd34d; padding: 0 3px; border-radius: 2px; margin-left: 2px; text-transform: uppercase; }

.section-buttons {
  margin-top: 12px; display: flex; gap: 6px;
}
.canvas-open-row { margin-top: 12px; }
.canvas-open-row .section-btn { width: 100%; }
.section-btn {
  flex: 1; padding: 8px 12px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.08);
  background: rgba(255,255,255,0.03); color: var(--text); cursor: pointer;
  font-size: 12px; text-align: center;
  transition: border-color 0.15s;
}
.section-btn:hover { border-color: rgba(255,255,255,0.15); background: rgba(255,255,255,0.05); }
.section-count { font-size: 10px; color: var(--text-dim); margin-left: 4px; }

.projections-section { margin-top: 12px; }
.projection-list { display: flex; flex-direction: column; gap: 4px; }
.projection-row { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border: 1px solid rgba(255,255,255,0.08); border-radius: 4px; background: rgba(255,255,255,0.02); }
.proj-name { flex: 1; font-size: 12px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.proj-universe { font-size: 11px; color: var(--text-dim); }
.proj-type { font-size: 10px; text-transform: uppercase; color: var(--text-dim); padding: 1px 6px; border-radius: 3px; background: rgba(255,255,255,0.04); }
.proj-type.active { color: #93c5fd; background: rgba(64,136,212,0.18); }
.proj-remove { background: transparent; border: none; color: var(--text-dim); cursor: pointer; font-size: 12px; }
.proj-remove:hover { color: #e06060; }
.projection-add { display: flex; gap: 6px; margin-top: 8px; }
.proj-input { flex: 1; padding: 6px 8px; border: 1px solid rgba(255,255,255,0.08); border-radius: 4px; background: var(--bg-input); color: var(--text); font-size: 12px; }
.proj-type-select { padding: 6px; border: 1px solid rgba(255,255,255,0.08); border-radius: 4px; background: var(--bg-input); color: var(--text); font-size: 12px; }
.proj-add-btn { flex: 0 0 auto; padding: 6px 10px; }
.proj-picker { flex: 1; min-width: 0; }
.proj-thumb { width: 32px; height: 32px; object-fit: cover; border-radius: 4px; border: 1px solid rgba(255,255,255,0.12); flex: 0 0 auto; }
.proj-thumb-empty { display: flex; align-items: center; justify-content: center; font-size: 14px; color: var(--text-dim); background: rgba(255,255,255,0.04); }
.projection-row.drag-over { border-color: var(--accent); background: rgba(64,136,212,0.12); }
</style>
