<template>
  <div>
    <div class="form-actions top-actions">
      <div class="left-actions">
        <button class="sheet-edit-btn" @click="$emit('switch-to-sheet')">Sheet</button>
        <button class="imagen-btn" @click="$emit('imagen')" :disabled="imagening">🖼 Imagen</button>
      </div>
      <button class="danger-btn" @click="$emit('delete')">Delete</button>
    </div>
    <GmEntityForm
      :model-value="form"
      @update:model-value="onFormUpdate"
      :universes="universes"
      :location-entities="locationEntities"
      :parent-id="parentId"
      :entity-id="entityId"
      @update:parent-id="onParentUpdate"
      @upload-bg="(e) => $emit('upload-bg', e)"
    />
    <TraitEditor
      :traits="traitSettings"
      :available-traits="availableTraits"
      :adding="addingTrait"
      @add-trait="(i) => $emit('add-trait', i)"
      @remove-trait="(id) => $emit('remove-trait', id)"
    />
    <div class="image-gallery" v-if="images.length">
      <h4>Generated Images</h4>
      <div class="gallery-grid">
        <div v-for="img in images" :key="img.id" class="gallery-item" @click="openImage(img)">
          <img :src="img.image_type === 'animated' ? img.path_animated : img.path_large" :alt="img.image_type" loading="lazy" />
          <span class="gallery-label">{{ img.image_type }} — {{ img.width }}×{{ img.height }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import GmEntityForm from '@/components/gm/GmEntityForm.vue'
import TraitEditor from '@/components/gm/TraitEditor.vue'
import ImageViewer from '@/components/gm/ImageViewer.vue'

const props = defineProps({
  form: { type: Object, default: () => ({}) },
  universes: { type: Array, default: () => [] },
  locationEntities: { type: Array, default: () => [] },
  parentId: { type: String, default: null },
  entityId: { type: String, default: null },
  traitSettings: { type: Array, default: () => [] },
  availableTraits: { type: Array, default: () => [] },
  addingTrait: { type: Boolean, default: false },
  imagening: { type: Boolean, default: false },
  open: { type: Function, default: null },
})

const emit = defineEmits(['update:form', 'update:parent-id', 'upload-bg', 'add-trait', 'remove-trait', 'switch-to-sheet', 'delete', 'imagen', 'image-open'])

function onFormUpdate(v) { emit('update:form', v) }
function onParentUpdate(v) { emit('update:parent-id', v) }

function openImage(img) {
  if (!props.open) return
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
    },
    listeners: {
      'deleted': loadImages,
    },
  })
}

const images = ref([])
async function loadImages() {
  if (!props.entityId) return
  try {
    const r = await fetch(`/api/v1/imagen/${props.entityId}`)
    if (r.ok) { const d = await r.json(); images.value = d.images || [] }
  } catch (e) { /* ignore */ }
}
watch(() => props.entityId, loadImages, { immediate: true })

// Refresh when user returns from button click (image generation completes)
defineExpose({ refresh: loadImages })
</script>

<style scoped>
.form-actions { display: flex; gap: 6px; }
.top-actions { justify-content: space-between; margin-bottom: 4px; }
.left-actions { display: flex; gap: 6px; align-items: center; }
.sheet-edit-btn { background: var(--accent); color: #fff; font-size: 11px; padding: 4px 10px; border-radius: 4px; border: none; cursor: pointer; }
.imagen-btn { background: #8b5cf6; color: #fff; font-size: 11px; padding: 4px 10px; border-radius: 4px; border: none; cursor: pointer; }
.imagen-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.danger-btn { background: var(--danger); color: #fff; font-size: 11px; padding: 4px 10px; border-radius: 4px; border: none; cursor: pointer; }

.image-gallery { margin-top: 12px; }
.image-gallery h4 { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
.gallery-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 6px; }
.gallery-item { display: block; border: 1px solid rgba(255,255,255,0.08); border-radius: 4px; overflow: hidden; cursor: pointer; }
.gallery-item img { width: 100%; height: auto; display: block; }
.gallery-label { display: block; font-size: 9px; color: var(--text-dim); text-align: center; padding: 2px 4px; background: rgba(0,0,0,0.3); }
</style>
