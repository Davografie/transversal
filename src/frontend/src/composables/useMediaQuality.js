import { ref, computed } from 'vue'

const STORAGE_KEY = 'mediaQuality'
const VALID = ['auto', 'low', 'high']

function readStored() {
  const v = localStorage.getItem(STORAGE_KEY)
  return VALID.includes(v) ? v : 'auto'
}

// Module-level singleton so the settings overlay and every consumer share state.
const quality = ref(readStored())

function setQuality(v) {
  if (!VALID.includes(v)) v = 'auto'
  quality.value = v
  localStorage.setItem(STORAGE_KEY, v)
}

// Automatic detection via the Network Information API (Chromium-only).
function connectionIsSlow() {
  if (typeof navigator === 'undefined' || !navigator.connection) return false
  const c = navigator.connection
  if (c.saveData) return true
  return ['slow-2g', '2g', '3g'].includes(c.effectiveType)
}

const isLowQuality = computed(() => {
  if (quality.value === 'low') return true
  if (quality.value === 'high') return false
  return connectionIsSlow() // 'auto'
})

/**
 * Rewrite a static media URL's size variant (Original/Large/Small/Mini).
 * Animated files (.webm/.mp4) have no variants and are returned unchanged,
 * as are external/arbitrary URLs that don't match the variant pattern.
 */
function withVariant(url, size) {
  if (!url || typeof url !== 'string') return url
  if (/\.(webm|mp4)(\?|$)/i.test(url)) return url
  return url.replace(
    /_(Original|Large|Small|Mini)\.(webp|png|jpe?g)(\?.*)?$/i,
    `_${size}.$2$3`
  )
}

/**
 * Derive the static fallback for an animated media URL.
 *
 * The animate pipeline saves the static source under the same base filename
 * as the animated file, so a video URL maps deterministically to its sibling:
 *   /media/animated/{e}/{u}/{name}.webm  →  /media/imagen/{e}/{u}/{name}_Small.webp
 *
 * Returns '' when the URL isn't an animated file (or can't be mapped).
 */
function animatedStaticFallback(url) {
  if (!url || typeof url !== 'string') return ''
  const m = url.match(/^(\/media\/)animated(\/[^/]+\/[^/]+\/[^/]+)\.(webm|mp4)(\?.*)?$/i)
  if (!m) return ''
  return `${m[1]}imagen${m[2]}_Small.webp${m[4] || ''}`
}

/**
 * Apply the active quality preference to a media URL.
 * Low quality (auto-detected or forced):
 *   - animated files fall back to their static _Small sibling, else
 *   - static images drop to _Small.
 * Animated files with no static sibling would 404, so callers should fall
 * back to the original URL on load error (see animatedStaticFallback).
 */
function qualityUrl(url) {
  if (!isLowQuality.value) return url
  return animatedStaticFallback(url) || withVariant(url, 'Small')
}

export function useMediaQuality() {
  return { quality, isLowQuality, setQuality, withVariant, animatedStaticFallback, qualityUrl }
}
