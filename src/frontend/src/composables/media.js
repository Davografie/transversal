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
