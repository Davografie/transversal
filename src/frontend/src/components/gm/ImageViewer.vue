<template>
  <div class="image-viewer">
    <div class="viewer-actions">
      <button v-if="imageType !== 'animated'" class="animate-btn" @click="onAnimate" :disabled="animating || localJob != null">
        <span class="btn-label">{{ statusInfo.label }}</span>
        <span v-if="statusInfo.status" class="btn-status">{{ statusInfo.status }}</span>
      </button>
      <button class="delete-btn" @click="onDelete" :disabled="deleting">🗑 Delete</button>
    </div>
    <img :src="imageType === 'animated' && animatedSrc ? animatedSrc : src" :alt="alt" />
    <div v-if="imageType !== 'animated' && !localJob" class="motion-hint">
      <input v-model="motionHint" type="text" placeholder="Motion hint (optional) — e.g. 'hair blowing in wind'" />
    </div>
    <div class="image-meta">{{ alt }}</div>
    <div v-if="message" class="message">{{ message }}</div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'

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
const deleting = ref(false)
const message = ref('')
const motionHint = ref('')

// Independent job polling — Panel system props are static on open
const localJob = ref(null)
let _pollTimer = null

async function pollOwnJob() {
  if (!props.entityId) return
  try {
    const r = await fetch('/api/v1/imagen/jobs')
    if (r.ok) {
      const jobs = (await r.json()).jobs || {}
      const j = jobs[props.entityId]
      localJob.value = (j && j.type === 'animate') ? j : null
    }
  } catch {}
}

onMounted(() => { pollOwnJob(); _pollTimer = setInterval(pollOwnJob, 2000) })
onUnmounted(() => { clearInterval(_pollTimer) })

// When job completes, tell parent to refresh gallery
watch(localJob, (now, prev) => {
  if (prev && !now) emit('refresh')
})

const statusInfo = computed(() => {
  const j = localJob.value || props.animateJob
  if (!j) return { label: '🎬 Animate', status: '' }
  if (j.status === 'failed') return { label: '🎬 Animate', status: '!' }
  if (j.status === 'queued') return { label: 'Animating in', status: j.queue_position || '⋯' }
  return { label: 'Animating..', status: '⟳' }
})

async function onAnimate() {
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
.viewer-actions { display: flex; gap: 6px; justify-content: center; margin-bottom: 8px; }
.animate-btn { background: #f59e0b; color: #fff; font-size: 11px; padding: 0; border-radius: 4px; border: none; cursor: pointer; display: inline-flex; overflow: hidden; }
.animate-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.animate-btn .btn-label { padding: 4px 8px; }
.animate-btn .btn-status { padding: 4px 8px; background: rgba(0,0,0,0.25); font-weight: 600; }
.delete-btn { background: var(--danger); color: #fff; font-size: 11px; padding: 4px 10px; border-radius: 4px; border: none; cursor: pointer; }
.delete-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.image-viewer img { max-width: 100%; max-height: 60vh; border-radius: 4px; }
.image-meta { font-size: 10px; color: var(--text-dim); margin-top: 6px; }
.message { font-size: 11px; color: var(--accent); margin-top: 6px; }
.motion-hint { margin-top: 8px; }
.motion-hint input { width: 100%; box-sizing: border-box; font-size: 11px; padding: 4px 8px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.06); color: var(--text); }
</style>
