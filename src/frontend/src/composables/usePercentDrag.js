/**
 * Dragging a point around a pannable map, in image-space percentages.
 *
 * Everything the GM places on a location by hand does the same thing: a nav dot and
 * a trait chip are each one `{x, y}` entry in a position map on the location, moved
 * by dragging in arrange mode, clamped to the same band, and saved as the whole map
 * when the drag ends. Only three things differ — which map, which key, and where it
 * is written — so those are all a caller supplies. This exists because the two had
 * already been written twice; a third surface would have made it three.
 *
 * The listeners live on `document`, not the element: a drag routinely outruns the
 * thing being dragged, and a listener on the dot would stop receiving moves the
 * moment the pointer left it. Every end path — mouse and touch — removes them.
 *
 * Percentages are converted through the **map's own box** (`viewerEl`), so a drag is
 * one-to-one whatever the camera is doing, and the same clamp (`2`–`98`) keeps a
 * point grabbable at the edges of the scene.
 */

const CLAMP_MIN = 2
const CLAMP_MAX = 98

/**
 * @param {object}   opts
 * @param {Function} opts.enabled  getter — is dragging allowed right now? (arrange mode)
 * @param {object}   opts.viewerEl ref to the map element the percentages are relative to
 * @returns {{ start: (event: Event, spec: object) => void }}
 *   `spec` is `{ x, y, onMove, onEnd }`: the entry's current position, a callback for
 *   each live position, and an optional callback once the drag has finished (where a
 *   caller saves). `onMove` receives already-clamped, already-rounded percentages.
 */
export function usePercentDrag({ enabled, viewerEl, span }) {
  function start(e, { x, y, onMove, onEnd }) {
    if (typeof enabled === 'function' ? !enabled() : !enabled) return
    const el = viewerEl?.value
    if (!el || !onMove) return
    e.preventDefault()

    // Both measured once per drag: neither can change meaningfully mid-drag, and
    // re-measuring on every move would force layout on the hot path.
    const rect = el.getBoundingClientRect()
    // The px size that **100% of the position space** spans — NOT the viewer's box.
    // Every map element is positioned as a percentage of the scene layer, which is
    // larger than the viewer (overscan ×1.1, plus the teaser zoom). Dividing by the
    // viewer instead makes the dragged thing move `scene ÷ viewer` times faster than
    // the pointer — measured at 1.19× for a square background and 2.11× for a wide
    // one, i.e. the chip visibly outruns the cursor. Callers whose positions are
    // image-space must pass this.
    const extent = span ? span() : { w: rect.width, h: rect.height }
    const clientX = e.touches ? e.touches[0].clientX : e.clientX
    const clientY = e.touches ? e.touches[0].clientY : e.clientY
    const clamp = (v) => Math.max(CLAMP_MIN, Math.min(CLAMP_MAX, Math.round(v)))

    function move(ev) {
      ev.preventDefault()
      const cx = ev.touches ? ev.touches[0].clientX : ev.clientX
      const cy = ev.touches ? ev.touches[0].clientY : ev.clientY
      onMove(
        clamp(x + ((cx - clientX) / extent.w) * 100),
        clamp(y + ((cy - clientY) / extent.h) * 100),
      )
    }

    async function end() {
      document.removeEventListener('mousemove', move)
      document.removeEventListener('mouseup', end)
      document.removeEventListener('touchmove', move)
      document.removeEventListener('touchend', end)
      if (onEnd) await onEnd()
    }

    document.addEventListener('mousemove', move)
    document.addEventListener('mouseup', end)
    document.addEventListener('touchmove', move, { passive: false })
    document.addEventListener('touchend', end)
  }

  return { start }
}
