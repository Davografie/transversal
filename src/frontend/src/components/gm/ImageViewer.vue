<template>
  <div class="image-viewer">
    <div class="viewer-actions">
      <button v-if="imageType !== 'animated'" class="animate-btn" @click="onAnimate" :disabled="animating">🎬 Animate</button>
      <button class="delete-btn" @click="onDelete" :disabled="deleting">🗑 Delete</button>
    </div>
    <img :src="imageType === 'animated' && animatedSrc ? animatedSrc : src" :alt="alt" />
    <div class="image-meta">{{ alt }}</div>
    <div v-if="message" class="message">{{ message }}</div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  src: { type: String, required: true },
  alt: { type: String, default: '' },
  entityId: { type: String, default: '' },
  imageId: { type: String, default: '' },
  imageType: { type: String, default: '' },
  animatedSrc: { type: String, default: '' },
})

const emit = defineEmits(['close', 'deleted'])
const animating = ref(false)
const deleting = ref(false)
const message = ref('')

async function onAnimate() {
  if (!props.entityId || animating.value) return
  animating.value = true
  message.value = 'Starting animation...'
  try {
    const r = await fetch(`/api/v1/animate/${props.entityId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_id: props.imageId }),
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
.animate-btn { background: #f59e0b; color: #fff; font-size: 11px; padding: 4px 10px; border-radius: 4px; border: none; cursor: pointer; }
.animate-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.delete-btn { background: var(--danger); color: #fff; font-size: 11px; padding: 4px 10px; border-radius: 4px; border: none; cursor: pointer; }
.delete-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.image-viewer img { max-width: 100%; max-height: 60vh; border-radius: 4px; }
.image-meta { font-size: 10px; color: var(--text-dim); margin-top: 6px; }
.message { font-size: 11px; color: var(--accent); margin-top: 6px; }
</style>
