<template>
  <div class="image-viewer">
    <MediaImage :src="imageType === 'animated' && animatedSrc ? animatedSrc : src" class="viewer-media" :alt="alt" />

    <div class="animate-section" v-if="imageType !== 'animated'">
      <div class="motion-hint-row">
        <input v-if="!statusInfo.cancelling" v-model="motionHint" type="text" placeholder="Motion hint (optional) — e.g. 'hair blowing in wind'" />
        <button class="animate-btn" :class="{ cancelling: statusInfo.cancelling }" @click="onAnimateClick">
          <span class="btn-label">{{ statusInfo.label }}</span>
          <span v-if="statusInfo.status" class="btn-status">{{ statusInfo.status }}</span>
        </button>
      </div>
      <div class="bg-remove-row" v-if="imageType !== 'cutout'">
        <button class="bg-btn" @click="onRemoveBgClick" :disabled="bgBusy || !!localBgJob">
          <span class="btn-label">{{ bgLabel }}</span>
        </button>
      </div>
    </div>
    <div class="role-assign">
      <label class="role-check" title="Use as background"><input type="checkbox" :checked="hasRole('background')" @change="toggleRole('background')" /> BG</label>
      <label class="role-check" title="Use as character sheet portrait"><input type="checkbox" :checked="hasRole('sheet')" @change="toggleRole('sheet')" /> Sheet</label>
      <label class="role-check" title="Use as navigation dot"><input type="checkbox" :checked="hasRole('navdot')" @change="toggleRole('navdot')" /> Nav</label>
    </div>
    <div class="universe-assign">
      <label class="universe-label">Universe</label>
      <select v-model="imageUniverse" class="universe-select" @change="onUniverseChange">
        <option v-for="u in availableUniverses" :key="u.key" :value="u.key">{{ u.name }}</option>
      </select>
    </div>
    <div class="image-meta">{{ alt }}<span v-if="fileExt" class="meta-ext"> · {{ fileExt }}</span><span v-if="sizeBytes" class="meta-size"> · {{ formatBytes(sizeBytes) }}</span></div>
    <div v-if="message" class="message">{{ message }}</div>

    <div class="danger-zone">
      <h4>Danger Zone</h4>
      <div class="danger-actions">
        <button class="delete-btn" @click="onDelete" :disabled="deleting">🗑 Delete</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import MediaImage from '@/components/MediaImage.vue'

const props = defineProps({
  src: { type: String, required: true },
  alt: { type: String, default: '' },
  entityId: { type: String, default: '' },
  imageId: { type: String, default: '' },
  imageType: { type: String, default: '' },
  animateJob: { type: Object, default: null },
  animatedSrc: { type: String, default: '' },
})

const emit = defineEmits(['close', 'deleted', 'refresh'])
const animating = ref(false)

const activeSrc = computed(() => props.imageType === 'animated' && props.animatedSrc ? props.animatedSrc : props.src)
const fileExt = computed(() => { const m = activeSrc.value.match(/\.(\w+)(\?|$)/); return m ? m[1] : '' })

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return ''
  return bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`
}
const deleting = ref(false)
const message = ref('')
const motionHint = ref('')
const fetchedRoles = ref([])

async function fetchRoles() {
  if (!props.entityId || !props.imageId) return
  try {
    const r = await fetch(`/api/v1/imagen/${props.entityId}`)
    if (r.ok) {
      const data = await r.json()
      const img = (data.images || []).find(i => i.id === props.imageId)
      if (img) fetchedRoles.value = img.roles || []
    }
  } catch {}
}
onMounted(() => { fetchRoles(); fetchUniverses(); fetchImageUniverse() })

// Universe assignment
const imageUniverse = ref('')
const availableUniverses = ref([])

async function fetchUniverses() {
  try {
    const r = await fetch('/api/v1/graphql', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: '{ entities(type: UNIVERSE) { id name currentUniverse } }' }),
    })
    if (r.ok) {
      const data = await r.json()
      availableUniverses.value = (data.data?.entities || []).map(e => ({ key: e.currentUniverse, name: e.name }))
    }
  } catch {}
}

async function fetchImageUniverse() {
  if (!props.entityId || !props.imageId) return
  try {
    const r = await fetch(`/api/v1/imagen/${props.entityId}`)
    if (r.ok) {
      const data = await r.json()
      const img = (data.images || []).find(i => i.id === props.imageId)
      if (img) imageUniverse.value = img.universe || ''
    }
  } catch {}
}

async function onUniverseChange() {
  try {
    await fetch(`/api/v1/imagen/${props.imageId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ universe: imageUniverse.value }),
    })
    emit('refresh')
  } catch {}
}

function hasRole(r) { return fetchedRoles.value.includes(r) }
async function toggleRole(r) {
  const current = fetchedRoles.value
  const next = current.includes(r) ? current.filter(x => x !== r) : [...current, r]
  fetchedRoles.value = next
  try {
    await fetch(`/api/v1/imagen/${props.imageId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roles: next }),
    })
    emit('refresh')
  } catch {}
}

// Independent job polling — Panel system props are static on open
const localJob = ref(null)
const localBgJob = ref(null)
let _pollTimer = null

async function pollOwnJob() {
  if (!props.entityId) return
  try {
    const r = await fetch('/api/v1/imagen/jobs')
    if (r.ok) {
      const jobs = (await r.json()).jobs || {}
      const j = jobs[props.entityId]
      localJob.value = (j && j.type === 'animate') ? j : null
      localBgJob.value = (j && j.type === 'remove_bg') ? j : null
    }
  } catch {}
}

onMounted(() => { pollOwnJob(); _pollTimer = setInterval(pollOwnJob, 2000) })
onUnmounted(() => { clearInterval(_pollTimer) })

// When job completes, tell parent to refresh gallery
watch(localJob, (now, prev) => {
  if (prev && !now) emit('refresh')
})
watch(localBgJob, (now, prev) => {
  if (prev && !now) emit('refresh')
})

// Background removal
const bgBusy = ref(false)
const bgLabel = computed(() => localBgJob.value ? 'Removing background…' : '🧼 Remove BG')

async function onRemoveBgClick() {
  if (bgBusy.value || localBgJob.value) return
  bgBusy.value = true
  message.value = 'Removing background…'
  try {
    const r = await fetch(`/api/v1/remove-background/${props.entityId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_id: props.imageId }),
    })
    const d = await r.json()
    message.value = d.accepted ? 'Background removal started — check gallery when complete' : (d.detail || 'Failed')
  } catch {
    message.value = 'Request failed'
  } finally {
    bgBusy.value = false
  }
}

const statusInfo = computed(() => {
  const j = localJob.value || props.animateJob
  if (!j) return { label: '🎬 Animate', status: '', cancelling: false }
  if (j.status === 'failed') return { label: '🎬 Animate', status: '!', cancelling: false }
  return { label: 'Cancel', status: '✕', cancelling: true }
})

function onAnimateClick() {
  if (statusInfo.value.cancelling) cancelAnimate()
  else startAnimate()
}

async function startAnimate() {
  if (!props.entityId || animating.value) return
  animating.value = true
  message.value = 'Starting animation...'
  try {
    const r = await fetch(`/api/v1/animate/${props.entityId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_id: props.imageId, motion_hint: motionHint.value }),
    })
    const d = await r.json()
    message.value = d.accepted ? 'Animation started — check gallery when complete' : 'Failed'
  } catch {
    message.value = 'Request failed'
  } finally {
    animating.value = false
  }
}

async function cancelAnimate() {
  if (!props.entityId) return
  try {
    await fetch(`/api/v1/imagen/${props.entityId}/cancel`, { method: 'POST' })
    message.value = 'Cancelled'
  } catch {
    message.value = 'Cancel failed'
  }
}

async function onDelete() {
  if (!props.imageId || deleting.value) return
  deleting.value = true
  try {
    const r = await fetch(`/api/v1/imagen/${props.imageId}`, { method: 'DELETE' })
    if (r.ok) {
      emit('deleted')
      emit('close')
    } else {
      message.value = 'Delete failed'
    }
  } catch {
    message.value = 'Request failed'
  } finally {
    deleting.value = false
  }
}
</script>

<style scoped>
.image-viewer { text-align: center; }
.image-viewer img { max-width: 100%; max-height: 60vh; border-radius: 4px; }
.viewer-video, .viewer-media { max-width: 100%; max-height: 60vh; border-radius: 4px; }

.animate-section { margin-top: 8px; }
.motion-hint-row { display: flex; gap: 6px; align-items: center; }
.motion-hint-row input { flex: 1; font-size: 11px; padding: 4px 8px; border-radius: 4px; border: 1px solid var(--overlay-12); background: var(--overlay-6); color: var(--text); }
.animate-btn { background: var(--amber); color: var(--text-on-accent); font-size: 11px; padding: 0; border-radius: 4px; border: none; cursor: pointer; display: inline-flex; overflow: hidden; white-space: nowrap; }
.animate-btn.cancelling { background: var(--danger-strong); }
.animate-btn .btn-label { padding: 4px 8px; }
.animate-btn .btn-status { padding: 4px 8px; background: rgba(0,0,0,0.25); font-weight: 600; }

.bg-remove-row { display: flex; justify-content: center; margin-top: 6px; }
.bg-btn { background: var(--overlay-10); color: var(--text); font-size: 11px; padding: 0; border-radius: 4px; border: 1px solid var(--overlay-16); cursor: pointer; display: inline-flex; overflow: hidden; white-space: nowrap; }
.bg-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.bg-btn .btn-label { padding: 4px 8px; }

.role-assign { display: flex; gap: 8px; justify-content: center; margin-top: 6px; }
.section-label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; }
.role-check { font-size: 10px; color: var(--text-dim); cursor: pointer; display: flex; align-items: center; gap: 2px; }
.role-check input { margin: 0; cursor: pointer; }

.universe-assign { display: flex; gap: 6px; justify-content: center; align-items: center; margin-top: 4px; }
.universe-label { font-size: 9px; color: var(--text-dim); text-transform: uppercase; }
.universe-select { font-size: 10px; padding: 2px 6px; border-radius: 3px; border: 1px solid var(--overlay-10); background: var(--overlay-4); color: var(--text); }

.image-meta { font-size: 10px; color: var(--text-dim); margin-top: 6px; }
.meta-size { color: var(--accent); }
.meta-ext { color: var(--text-dim); text-transform: uppercase; }
.message { font-size: 11px; color: var(--accent); margin-top: 6px; }

.danger-zone {
  margin-top: 12px; padding: 10px;
  border: 1px solid var(--danger-20); border-radius: 6px;
  background: var(--danger-8); text-align: left;
}
.danger-zone h4 {
  font-size: 10px; color: var(--danger-soft); text-transform: uppercase; letter-spacing: 1px;
  margin: 0 0 8px 0;
}
.danger-actions { display: flex; gap: 6px; }
.delete-btn { background: var(--danger); color: var(--text-on-accent); font-size: 11px; padding: 4px 10px; border-radius: 4px; border: none; cursor: pointer; }
.delete-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
