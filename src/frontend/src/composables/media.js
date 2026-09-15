// Pure, framework-free media helpers shared across the renderers.
//
// The img/video decision and the background-panning axis are duplicated across
// several components (MediaImage, MapDot, LocationViewer, useMediaQuality).
// Centralising them keeps the "is this animated?" and "which way do we pan?"
// logic in one place.

/**
 * True when `url` points to an animated video file (.webm / .mp4).
 * Static images (webp/png/jpg) and empty/arbitrary values return false.
 */
export function isVideoUrl(url) {
  return !!url && /\.(webm|mp4)(\?|$)/i.test(url)
}

/**
 * Resolve a media URL's intrinsic aspect ratio (width / height), or null when
 * it cannot be decoded. Handles stills and video backgrounds alike: an
 * `HTMLImageElement` cannot decode .webm/.mp4, so videos are probed through a
 * metadata-only `<video>`. This is the one DOM-touching helper here — the rest
 * of the module stays pure.
 */
export function probeAspect(url) {
  if (!url) return Promise.resolve(null)
  if (isVideoUrl(url)) {
    return new Promise((resolve) => {
      const vid = document.createElement('video')
      vid.preload = 'metadata'
      vid.onloadedmetadata = () => resolve((vid.videoWidth / vid.videoHeight) || null)
      vid.onerror = () => resolve(null)
      vid.src = url
    })
  }
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => resolve((img.width / img.height) || null)
    img.onerror = () => resolve(null)
    img.src = url
  })
}

/**
 * Warm a media URL so a renderer can paint it without a blank frame.
 *
 * Stills resolve once the bytes are *decoded* — `decode()`, not merely fetched,
 * because a cache hit still has to decode before it can paint. Videos resolve
 * once a first frame is buffered (`loadeddata`). This is the video-aware
 * counterpart to `probeAspect`: an `<img>` cannot decode a .webm, which is why
 * animated destinations used to flash black on arrival.
 *
 * Always settles — to the warm element, or `null` on error/timeout — so a broken
 * or slow asset can never strand a transition.
 */
export function preloadMedia(url, { timeout = 2000 } = {}) {
  if (!url) return Promise.resolve(null)
  const video = isVideoUrl(url)
  const el = video ? document.createElement('video') : new Image()
  if (video) {
    el.preload = 'auto'
    el.muted = true
    el.playsInline = true
  }
  const ready = new Promise((resolve) => {
    if (video) {
      if (el.readyState >= 2) { resolve(true); return }  // HAVE_CURRENT_DATA
      el.onloadeddata = () => resolve(true)
      el.onerror = () => resolve(false)
    } else {
      el.onload = () => {
        if (!el.decode) { resolve(true); return }
        el.decode().then(() => resolve(true), () => resolve(false))
      }
      el.onerror = () => resolve(false)
    }
  })
  el.src = url
  return Promise.race([
    ready,
    new Promise((resolve) => setTimeout(() => resolve(false), timeout)),
  ]).then((ok) => (ok ? el : null))
}

/**
 * Decide the background-pan axis from image and viewport aspect ratios.
 *
 * Returns:
 *   'x'  — image is wider than the viewport → pan horizontally
 *   'y'  — image is taller than the viewport → pan vertically
 *   null — aspect unknown or square → default behaviour
 */
export function panAxis(imageAspect, viewAspect) {
  if (imageAspect && imageAspect > viewAspect) return 'x'
  if (imageAspect && imageAspect < viewAspect) return 'y'
  return null
}

/**
 * Overscan factor applied to scene backgrounds: the image is always rendered
 * larger than the viewport on BOTH axes so panning works horizontally and
 * vertically (the hole-through-the-world parallax needs both axes).
 */
export const PAN_OVERSCAN = 1.1

/**
 * px size that covers the viewport at the given image aspect, overscanned by
 * PAN_OVERSCAN on both axes.
 */
export function coverOverscan(vw, vh, aspect) {
  const coverW = Math.max(vw, vh * aspect)
  const coverH = Math.max(vh, vw / aspect)
  return { w: coverW * PAN_OVERSCAN, h: coverH * PAN_OVERSCAN }
}
