<script setup>
import { computed, useAttrs } from 'vue'
import { useEntityMedia } from '@/composables/useEntityMedia.js'
import { isVideoUrl } from '@/composables/media.js'

/**
 * Unified media renderer for the element mode (img vs video).
 *
 * Two ways to supply the source:
 *   - `src` — an already-known media URL.
 *   - `entity-id` + `role` — query the entity's role-tagged image
 *     (role: 'background' | 'sheet' | 'navdot') and render it. The
 *     composable applies quality/cache resolution.
 *
 * Video (.webm/.mp4) renders a <video> with autoplay/loop/muted/playsinline;
 * everything else renders an <img>. Class/style/other attrs are forwarded to
 * the underlying element, so each caller's scoped CSS keeps working.
 */
const props = defineProps({
  src: { type: String, default: '' },
  entityId: { type: String, default: '' },
  role: { type: String, default: '' },
  alt: { type: String, default: '' },
  lazy: { type: Boolean, default: false },
  // Explicit ARIA role for interactive media (e.g. a clickable portrait).
  // Separate from `role`, which is the media role tag used for querying.
  ariaRole: { type: String, default: '' },
})

defineOptions({ inheritAttrs: false })
const attrs = useAttrs()

const { src: queriedSrc } = useEntityMedia(
  computed(() => props.entityId),
  props.role
)

const effectiveSrc = computed(() =>
  props.entityId && props.role ? queriedSrc.value : props.src
)
const isVideo = computed(() => isVideoUrl(effectiveSrc.value))

// Single dynamic root so the parent's scoped CSS still reaches this element.
const tag = computed(() => (isVideo.value ? 'video' : 'img'))
const elementAttrs = computed(() => {
  const base = { ...attrs, src: effectiveSrc.value }
  if (props.ariaRole) base.role = props.ariaRole
  if (isVideo.value) {
    return { ...base, autoplay: true, loop: true, muted: true, playsinline: true }
  }
  return {
    ...base,
    alt: props.alt,
    loading: props.lazy ? 'lazy' : undefined,
  }
})
</script>

<template>
  <component :is="tag" v-if="effectiveSrc" v-bind="elementAttrs" />
</template>
