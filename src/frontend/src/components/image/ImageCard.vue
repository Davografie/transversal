<template>
  <div
    class="image-card"
    :class="{ selected }"
    :data-img-path="thumbSrc(image)"
    :draggable="draggable"
    @contextmenu.prevent
    @dragstart="draggable && $emit('dragstart', $event, image.id)"
    @dragend="draggable && $emit('dragend', $event)"
    @touchstart="draggable && $emit('touchstart', $event, image.id)"
    @click="$emit('open', image)"
  >
    <MediaImage :src="thumbSrc(image)" class="image-card-thumb" :alt="caption(image)" lazy />
    <span class="image-card-label">
      {{ caption(image) }}
      <span v-if="image.universe_label" class="universe-badge">{{ image.universe_label }}</span>
      <span v-for="r in image.roles || []" :key="r" class="role-badge">{{ r }}</span>
      <!-- Derived renders ([[B210]]): a matte and a loop belong to the picture, so
           they badge it rather than appearing as pictures of their own. -->
      <span v-for="r in image.renders || []" :key="'render-' + r" class="render-badge">{{ r }}</span>
      <!-- The XLarge tier is real detail only once the master reaches the ceiling. -->
      <span
        v-if="image.can_upscale === false"
        class="xl-badge"
        title="At the 2048px ceiling — the XLarge tier is real detail"
      >XL</span>
      <span
        v-for="f in autoFlags(image)"
        :key="f"
        class="flag-badge"
        :title="f === 'ai_generated' ? 'Made by the imagen pipeline' : 'Motion made by the animate pipeline'"
      >{{ AUTO_FLAG_LABELS[f] }}</span>
      <span v-if="hasFlag(image, 'ai')" class="flag-badge" title="AI was somewhere in this picture's workflow">AI</span>
    </span>
  </div>
</template>

<script setup>
/**
 * One picture, as a gallery shows it: the thumbnail, the caption, and every tag
 * that describes it — roles, derived renders, the XL tier and the AI labels.
 *
 * Read-only on purpose. [[B211]] made the **viewer** the one place a picture is
 * edited, so a card never has to know how to write anything, and the trait
 * editor's separate set of checkboxes could go.
 */
import MediaImage from '@/components/MediaImage.vue'
import { AUTO_FLAG_LABELS, autoFlags, caption, hasFlag, thumbSrc } from './imageMeta.js'

defineProps({
  image: { type: Object, required: true },
  selected: { type: Boolean, default: false },
  draggable: { type: Boolean, default: true },
})

defineEmits(['open', 'dragstart', 'dragend', 'touchstart'])
</script>

<style scoped>
.image-card {
  display: block; border: 1px solid var(--overlay-8); border-radius: 4px;
  overflow: hidden; cursor: pointer;
  -webkit-touch-callout: none; -webkit-user-select: none; user-select: none;
}
.image-card.selected { outline: 2px solid var(--accent); outline-offset: -2px; }
.image-card-thumb { width: 100%; height: auto; display: block; -webkit-user-drag: none; }
.image-card-label {
  display: block; font-size: 9px; color: var(--text-dim); text-align: center;
  padding: 2px 4px; background: rgba(0, 0, 0, 0.3);
}
.universe-badge { display: inline-block; font-size: 7px; background: var(--resource-32); color: var(--violet-pale); padding: 0 3px; border-radius: 2px; margin-left: 3px; }
.role-badge { display: inline-block; font-size: 7px; background: var(--warn-32); color: var(--gold); padding: 0 3px; border-radius: 2px; margin-left: 2px; text-transform: uppercase; }
.render-badge { display: inline-block; font-size: 7px; background: rgba(120, 200, 160, 0.30); color: var(--text); padding: 0 3px; border-radius: 2px; margin-left: 2px; text-transform: uppercase; }
.xl-badge { display: inline-block; font-size: 7px; background: rgba(108, 140, 255, 0.32); color: var(--text); padding: 0 3px; border-radius: 2px; margin-left: 2px; font-weight: 600; }
.flag-badge { display: inline-block; font-size: 7px; background: var(--overlay-12); color: var(--text); padding: 0 3px; border-radius: 2px; margin-left: 2px; }
</style>
