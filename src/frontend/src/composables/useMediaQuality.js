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
 * Apply the active quality preference to a media URL.
 * Low quality (auto-detected or forced) drops static images to `_Small`.
 */
function qualityUrl(url) {
  return isLowQuality.value ? withVariant(url, 'Small') : url
}

export function useMediaQuality() {
  return { quality, isLowQuality, setQuality, withVariant, qualityUrl }
}
