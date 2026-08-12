<template>
  <div>
    <GmEntityForm
      :model-value="form"
      :entity-id="entityId"
      @update:model-value="onFormUpdate"
    />
    <div class="image-gallery">
      <div class="gallery-header">
        <h4>Images</h4>
        <div class="gallery-actions">
          <label class="upload-btn">
            📤 Upload
            <input type="file" accept="image/*" @change="$emit('upload-bg', $event)" hidden />
          </label>
          <button class="imagen-btn" :class="{ cancelling: imagenStatus.cancelling }" @click="onImagenClick">
            <span class="btn-label">{{ imagenStatus.label }}</span>
            <span v-if="imagenStatus.status" class="btn-status">{{ imagenStatus.status }}</span>
          </button>
        </div>
      </div>
      <div v-if="!images.length" class="gallery-empty">No images yet — upload or generate one.</div>
      <div v-else class="gallery-grid">
        <div v-for="img in images" :key="img.id" class="gallery-item" @click="openImage(img)">
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
    <div v-if="form.type === 'UNIVERSE'" class="section-buttons">
      <button class="section-btn" @click="openLoraConfig">🖼 LoRA Configuration</button>
      <button class="section-btn" @click="openLifePaths">📋 Life Paths <span v-if="lifePaths.length" class="section-count">{{ lifePaths.length }}</span></button>
    </div>
    <div class="danger-zone">
      <h4>Danger Zone</h4>
      <div class="danger-actions">
        <button
          class="danger-btn" :class="{ confirming: confirmingDelete }"
          @click="onDeleteClick"
        >{{ confirmingDelete ? 'Confirm?' : 'Delete' }}</button>
        <button
          v-if="form.type === 'LOCATION'"
          class="prune-btn" :class="{ confirming: confirmingPrune }"
          @click="onPruneClick"
        >{{ confirmingPrune ? 'Confirm?' : 'Prune' }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, useAttrs, onMounted, onUnmounted } from 'vue'
import { useApi } from '@/composables/useApi.js'
import GmEntityForm from '@/components/gm/GmEntityForm.vue'
import ImageViewer from '@/components/gm/ImageViewer.vue'
import GmLoRAConfigPanel from '@/components/gm/GmLoRAConfigPanel.vue'
import GmLifePathsPanel from '@/components/gm/GmLifePathsPanel.vue'

const CONFIRM_TIMEOUT = 3000

const { graphql } = useApi()
const lifePaths = ref([])
const loadingLifepaths = ref(false)

async function loadLifePaths(universeKey) {
  if (!universeKey) return
  loadingLifepaths.value = true
  try {
    const data = await graphql(
      `query($u: String!) {
        lifePaths(universe: $u) {
          id name universe description
          qualification { traitId difficulty mustBeAtLocation draft }
          discovery { atLocation knowsEntity possessesTrait hasTraitRating hasRelationship }
          curriculum { traitId createAt stepUp minRank }
          survival { traitIds difficulty termPenaltyAfter mishaps }
          events { description effect minRank }
          advancement { traitIds difficulty ranks { number name benefits } }
          musterOut { perTermBenefits atRanks }
        }
      }`,
      { u: universeKey }
    )
    lifePaths.value = data?.lifePaths || []
  } catch {
    lifePaths.value = []
  } finally {
    loadingLifepaths.value = false
  }
}

const props = defineProps({
  form: { type: Object, default: () => ({}) },
  entityId: { type: String, default: null },
  imagenJob: { type: Object, default: null },
  animateJob: { type: Object, default: null },
  open: { type: Function, default: null },
  close: { type: Function, default: null },
  traitNameMap: { type: Object, default: () => ({}) },
})

function openLoraConfig() {
  if (!props.open) return
  props.open({
    component: GmLoRAConfigPanel,
    title: 'LoRA Configuration',
    props: { loraConfigJson: props.form.lora_config || '{}' },
    listeners: {
      'update:loraConfig': (json) => emit('update:form', { ...props.form, lora_config: json }),
    },
  })
}

function openLifePaths() {
  if (!props.open) return
  props.open({
    component: GmLifePathsPanel,
    title: 'Life Paths',
    props: { universe: props.form?.current_universe || props.entityId, open: props.open, close: props.close },
  })
}

const emit = defineEmits(['update:form', 'upload-bg', 'switch-to-sheet', 'delete', 'prune', 'imagen', 'cancel', 'image-open'])

// Load life paths when editing a universe entity
watch(() => [props.entityId, props.form?.type], ([id, type]) => {
  if (id && type === 'UNIVERSE') loadLifePaths(props.form.current_universe || props.entityId)
}, { immediate: true })

// Independent job polling — props are snapshots from the panel system
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
  const j = localImagenJob.value || props.imagenJob
  if (!j) return { label: '🖼 Imagen', status: '', cancelling: false }
  if (j.status === 'failed') return { label: '🖼 Imagen', status: '!', cancelling: false }
  return { label: 'Cancel', status: '✕', cancelling: true }
})

function onImagenClick() {
  if (imagenStatus.value.cancelling) emit('cancel')
  else emit('imagen')
}

// Refresh gallery when a job completes
watch(localImagenJob, (now, prev) => {
  if (prev && !now) loadImages()
})

// ── Two-click confirmation (no dialogs) ────────────
const _confirmTimer = ref(null)
const confirmingDelete = ref(false)
const confirmingPrune = ref(false)

function onDeleteClick() {
  if (confirmingDelete.value) { clearTimeout(_confirmTimer.value); confirmingDelete.value = false; emit('delete') }
  else { confirmingDelete.value = true; _confirmTimer.value = setTimeout(() => { confirmingDelete.value = false }, CONFIRM_TIMEOUT) }
}
function onPruneClick() {
  if (confirmingPrune.value) { clearTimeout(_confirmTimer.value); confirmingPrune.value = false; emit('prune') }
  else { confirmingPrune.value = true; _confirmTimer.value = setTimeout(() => { confirmingPrune.value = false }, CONFIRM_TIMEOUT) }
}
onUnmounted(() => clearTimeout(_confirmTimer.value))

function formatSize(bytes) {
  if (!bytes || bytes === 0) return ''
  return bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`
}

// ── LoRA configuration (universe entities only) ─────
const imagenEntityTypes = ['CHARACTER', 'GMC', 'LOCATION', 'FACTION', 'ASSET']
const availableLoras = ref([])
const loraConfig = ref({})

async function fetchLoras() {
  try {
    const r = await fetch('/api/v1/imagen/loras')
    if (r.ok) {
      const d = await r.json()
      availableLoras.value = (d.loras || []).map(l => typeof l === 'string' ? { name: l, path: l } : l)
    }
  } catch {}
}

watch(() => props.form?.lora_config, (v) => {
  try { loraConfig.value = v ? JSON.parse(v) : {} } catch { loraConfig.value = {} }
}, { immediate: true })

function loraAt(entityType, idx) {
  const list = loraConfig.value[entityType] || []
  return list[idx] || ''
}

function setLora(entityType, idx, loraName) {
  const list = [...(loraConfig.value[entityType] || [])]
  while (list.length <= idx) list.push('')
  list[idx] = loraName
  // Compact: remove empty trailing entries
  while (list.length && !list[list.length - 1]) list.pop()
  loraConfig.value = { ...loraConfig.value, [entityType]: list }
  emit('update:form', { ...props.form, lora_config: JSON.stringify(loraConfig.value) })
}

function onFormUpdate(v) { emit('update:form', v) }
const openedImageId = ref(null)
const attrs = useAttrs()

function openImage(img) {
  if (!props.open) return
  if (openedImageId.value === img.id) {
    const closeFn = props.close || attrs.close
        if (closeFn) { closeFn(); openedImageId.value = null }
    return
  }
  openedImageId.value = img.id
  props.open({
    component: ImageViewer,
    title: img.image_type + ' — ' + img.id,
    props: {
      src: img.path_animated || img.path_large,
      animatedSrc: img.path_animated,
      alt: img.image_type + ' — ' + img.width + '×' + img.height,
      entityId: props.entityId,
      imageId: img.id,
      imageType: img.image_type,
      roles: img.roles || [],
      animateJob: props.animateJob,
      sizeBytes: img.size_bytes,
    },
    listeners: {
      'deleted': loadImages,
      'refresh': loadImages,
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
onMounted(() => {
  window.addEventListener('lifepath-saved', (e) => {
    if (props.form?.type === 'UNIVERSE') loadLifePaths(props.form.current_universe || props.entityId)
  })
})
onUnmounted(() => { clearInterval(_jobPollTimer) })
defineExpose({ refresh: loadImages })
</script>

<style scoped>
.imagen-btn { background: #8b5cf6; color: #fff; font-size: 11px; padding: 0; border-radius: 4px; border: none; cursor: pointer; display: inline-flex; overflow: hidden; }
.imagen-btn.cancelling { background: #dc2626; }
.imagen-btn .btn-label { padding: 4px 8px; }
.imagen-btn .btn-status { padding: 4px 8px; background: rgba(0,0,0,0.25); font-weight: 600; }
.danger-btn { background: var(--danger); color: #fff; font-size: 11px; padding: 4px 10px; border-radius: 4px; border: none; cursor: pointer; }
.prune-btn { background: #b03030; color: #fff; font-size: 11px; padding: 4px 10px; border-radius: 4px; border: none; cursor: pointer; margin-left: 4px; }
.prune-btn:hover { background: #d04040; }
.danger-btn.confirming,
.prune-btn.confirming { background: #fff; color: #b03030; font-weight: 600; animation: pulse-confirm 0.6s ease-in-out infinite alternate; }

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

@keyframes pulse-confirm {
  from { opacity: 0.85; }
  to { opacity: 1; }
}

.section-buttons {
  margin-top: 12px; display: flex; gap: 6px;
}
.section-btn {
  flex: 1; padding: 8px 12px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.08);
  background: rgba(255,255,255,0.03); color: var(--text); cursor: pointer;
  font-size: 12px; text-align: center;
  transition: border-color 0.15s;
}
.section-btn:hover { border-color: rgba(255,255,255,0.15); background: rgba(255,255,255,0.05); }
.section-count { font-size: 10px; color: var(--text-dim); margin-left: 4px; }
</style>
