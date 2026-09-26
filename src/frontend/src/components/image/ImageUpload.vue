<template>
  <span class="image-upload">
    <label class="image-upload-btn" :class="{ busy }" :title="title">
      <slot>{{ label }}</slot>
      <input type="file" accept="image/*" :disabled="busy || !ownerId" hidden @change="pick" />
    </label>
    <span v-if="error" class="image-upload-error">{{ error }}</span>
  </span>
</template>

<script setup>
/**
 * The one upload control ([[B211]]).
 *
 * It owns the file input, the multipart post and the error line, so a surface
 * only has to say **who** the picture belongs to — which is what the two previous
 * implementations disagreed about: one sent the legacy `entity_id`, swallowed
 * every failure and never refreshed; the other sent owners, surfaced the error
 * and refreshed. Neither is needed twice.
 */
import { ref } from 'vue'
import { uploadImage } from '@/composables/useImageGallery.js'

const props = defineProps({
  ownerKind: { type: String, default: 'entity' },
  ownerId: { type: String, default: '' },
  /** Stored with the picture for provenance; a trait needs it to be listed. */
  universe: { type: String, default: '' },
  /**
   * The rung below the owner this picture belongs to — a projection, or a
   * traitsetting whose picture overrides the registry trait's. Empty for the
   * owner's own definition picture.
   */
  variantId: { type: String, default: '' },
  label: { type: String, default: '📤 Upload' },
  title: { type: String, default: 'Upload an image' },
})

const emit = defineEmits(['uploaded', 'error'])

const busy = ref(false)
const error = ref('')

async function pick(event) {
  const file = event.target.files?.[0]
  event.target.value = ''  // let the same file be re-picked after a failure
  if (!file || !props.ownerId) return
  busy.value = true
  error.value = ''
  try {
    await uploadImage({
      kind: props.ownerKind,
      id: props.ownerId,
      universe: props.universe,
      variantId: props.variantId,
      file,
    })
    emit('uploaded')
  } catch (e) {
    error.value = e?.message || 'Upload failed'
    emit('error', e)
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.image-upload { display: inline-flex; align-items: center; gap: 6px; }
.image-upload-btn {
  font-size: 11px; padding: 4px 10px; border-radius: 4px;
  border: 1px solid var(--border); color: var(--text);
  display: inline-flex; align-items: center; cursor: pointer;
}
.image-upload-btn.busy { opacity: 0.6; cursor: progress; }
.image-upload-error { font-size: 10px; color: var(--danger-soft, #e07a7a); }
</style>
