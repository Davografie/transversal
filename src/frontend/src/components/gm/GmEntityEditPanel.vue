<template>
  <div>
    <div class="form-actions top-actions">
      <div class="left-actions">
        <button class="sheet-edit-btn" @click="$emit('switch-to-sheet')">Sheet</button>
        <button class="imagen-btn" @click="$emit('imagen')" :disabled="imagenJob != null">
          <span class="btn-label">{{ imagenStatus.label }}</span>
          <span v-if="imagenStatus.status" class="btn-status">{{ imagenStatus.status }}</span>
        </button>
      </div>
    </div>
    <GmEntityForm
      :model-value="form"
      :entity-id="entityId"
      @update:model-value="onFormUpdate"
      @upload-bg="$emit('upload-bg', $event)"
    />
    <div class="image-gallery" v-if="images.length">
      <h4>Generated Images</h4>
      <div class="gallery-grid">
        <div v-for="img in images" :key="img.id" class="gallery-item" @click="openImage(img)">
          <img :src="img.image_type === 'animated' ? img.path_animated : img.path_large" :alt="img.image_type" loading="lazy" />
          <span class="gallery-label">
            {{ img.image_type }} — {{ img.width }}×{{ img.height }}
            <span v-if="img.universe_label" class="universe-badge">{{ img.universe_label }}</span>
            <span v-for="r in img.roles" :key="r" class="role-badge">{{ r }}</span>
          </span>
        </div>
      </div>
    </div>
    <div class="danger-zone">
      <h4>Danger Zone</h4>
      <div class="danger-actions">
        <button class="danger-btn" @click="$emit('delete')">Delete</button>
        <button v-if="form.type === 'LOCATION'" class="prune-btn" @click="$emit('prune')">Prune</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, useAttrs } from 'vue'
import GmEntityForm from '@/components/gm/GmEntityForm.vue'
import ImageViewer from '@/components/gm/ImageViewer.vue'

const props = defineProps({
  form: { type: Object, default: () => ({}) },
  entityId: { type: String, default: null },
  imagenJob: { type: Object, default: null },
  animateJob: { type: Object, default: null },
  open: { type: Function, default: null },
})

const emit = defineEmits(['update:form', 'upload-bg', 'switch-to-sheet', 'delete', 'prune', 'imagen', 'image-open'])

const imagenStatus = computed(() => {
  const j = props.imagenJob
  if (!j) return { label: '🖼 Imagen', status: '' }
  if (j.status === 'failed') return { label: '🖼 Imagen', status: '!' }
  if (j.status === 'queued') return { label: 'Imagening in', status: j.queue_position || '⋯' }
  return { label: 'Imagening..', status: '⟳' }
})

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
defineExpose({ refresh: loadImages })
</script>

<style scoped>
.form-actions { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.left-actions { display: flex; gap: 6px; align-items: center; }
.sheet-edit-btn { background: var(--accent); color: #fff; font-size: 11px; padding: 4px 10px; border-radius: 4px; border: none; cursor: pointer; }
.imagen-btn { background: #8b5cf6; color: #fff; font-size: 11px; padding: 0; border-radius: 4px; border: none; cursor: pointer; display: inline-flex; overflow: hidden; }
.imagen-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.imagen-btn .btn-label { padding: 4px 8px; }
.imagen-btn .btn-status { padding: 4px 8px; background: rgba(0,0,0,0.25); font-weight: 600; }
.danger-btn { background: var(--danger); color: #fff; font-size: 11px; padding: 4px 10px; border-radius: 4px; border: none; cursor: pointer; }
.prune-btn { background: #b03030; color: #fff; font-size: 11px; padding: 4px 10px; border-radius: 4px; border: none; cursor: pointer; margin-left: 4px; }
.prune-btn:hover { background: #d04040; }

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
.image-gallery h4 { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
.gallery-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 6px; }
.gallery-item { display: block; border: 1px solid rgba(255,255,255,0.08); border-radius: 4px; overflow: hidden; cursor: pointer; }
.gallery-item img { width: 100%; height: auto; display: block; }
.gallery-label { display: block; font-size: 9px; color: var(--text-dim); text-align: center; padding: 2px 4px; background: rgba(0,0,0,0.3); }
.universe-badge { display: inline-block; font-size: 7px; background: rgba(139,92,246,0.3); color: #c4b5fd; padding: 0 3px; border-radius: 2px; margin-left: 3px; }
.role-badge { display: inline-block; font-size: 7px; background: rgba(245,158,11,0.3); color: #fcd34d; padding: 0 3px; border-radius: 2px; margin-left: 2px; text-transform: uppercase; }
</style>
