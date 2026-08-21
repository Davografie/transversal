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

/**
 * Cache-aware variant of `qualityUrl`.
 *
 * In low-quality mode we'd normally swap to a smaller URL, but if the client
 * already has the ORIGINAL (large/animated) file cached, showing it costs zero
 * bandwidth — so prefer the cached original and only downgrade on a cache miss.
 *
 * In high-quality mode (or when Cache Storage is unavailable, e.g. dev
 * without a service worker) this just returns `url` unchanged.
 */
async function resolveMediaUrl(url) {
  if (!isLowQuality.value) return url
  if (await isCached(url)) return url
  return qualityUrl(url)
}

/**
 * True when `url` is present in the browser's Cache Storage (populated by the
 * service worker's runtime caching). Returns false when the Cache API is
 * unavailable (e.g. dev server without a service worker) or on any error.
 */
async function isCached(url) {
  if (!url || typeof url !== 'string') return false
  if (typeof caches === 'undefined') return false
  try {
    // Cache keys are absolute request URLs; resolve relative /media/... paths.
    const absolute = new URL(url, window.location.origin).href
    return !!(await caches.match(absolute))
  } catch {
    return false
  }
}

export function useMediaQuality() {
  return { quality, isLowQuality, setQuality, withVariant, animatedStaticFallback, qualityUrl, resolveMediaUrl, isCached }
}
