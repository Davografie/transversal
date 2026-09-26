<template>
  <div class="image-gallery-root">
    <div v-if="!images.length" class="gallery-empty">{{ empty }}</div>
    <!-- One root, so a parent's native drop listeners fall through onto this
         element and `zoneClass` still marks the drop target for its own
         `closest()` lookup (the entity editor resolves a drop by that class). -->
    <div
      v-else
      class="gallery-grid"
      :class="[zoneClass, { 'drag-over': dropActive }]"
    >
      <ImageCard
        v-for="img in images"
        :key="img.id"
        :image="img"
        :selected="img.id === selectedId"
        :draggable="draggable"
        @open="$emit('open', $event)"
        @dragstart="(event, id) => $emit('dragstart', event, id)"
        @dragend="$emit('dragend', $event)"
        @touchstart="(event, id) => $emit('touchstart', event, id)"
      />
    </div>
  </div>
</template>

<script setup>
/**
 * A grid of pictures for one owner — the single gallery ([[B211]]).
 *
 * Drop handling is deliberately **not** here: the entity editor resolves a drop
 * by looking up an ancestor class (`entity-gallery-drop`, or a projection block),
 * so the parent keeps those listeners and passes the zone class in. The gallery
 * only knows how to draw its pictures and say which one is open.
 */
import ImageCard from './ImageCard.vue'

defineProps({
  images: { type: Array, default: () => [] },
  selectedId: { type: String, default: '' },
  empty: { type: String, default: 'No images yet.' },
  /** Extra class on the grid, so a parent can recognise it as a drop zone. */
  zoneClass: { type: String, default: '' },
  dropActive: { type: Boolean, default: false },
  draggable: { type: Boolean, default: true },
})

defineEmits(['open', 'dragstart', 'dragend', 'touchstart'])
</script>

<style scoped>
.gallery-empty { font-size: 10px; color: var(--text-dim); padding: 12px 0; text-align: center; }
.gallery-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 6px; }
</style>
