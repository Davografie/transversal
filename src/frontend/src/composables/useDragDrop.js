import { ref, onScopeDispose } from 'vue'

// One composable for both mouse (HTML5) drag-and-drop and touch long-press-
// and-drop. A surface declares *what* it drags and *where* it can drop via two
// callbacks; the composable owns the shared drag state and the touch long-press
// mechanics (hold → ghost → hit-test → drop).
//
//   resolveTarget(el) → payload | null   extract a drop payload from a DOM
//                                        element under the pointer (null if it
//                                        isn't a valid drop zone)
//   onCommit({ from, to })               apply the move once a drop lands
//
// `source` is whatever the consumer passes to `dragStart`/`touchStart` (a row
// index, a node object, …); `over` is the payload `resolveTarget` returned.
export function useDragDrop(options = {}) {
  const {
    engageDelay = 400,            // hold ms before a touch becomes a drag
    slop = 8,                     // px of movement that cancels a pending hold
    ghostOffset = { x: -20, y: -14 }, // ghost position relative to the touch point
    ghostSource = null,           // (el) => HTMLElement | null — element to clone (default: el)
    makeGhost = null,             // (el, touch) => HTMLElement | null — full override, own styling
    resolveTarget = () => null,   // (el) => payload | null
    onCommit = () => {},          // ({ from, to }) => void
  } = options

  const dragging = ref(false)
  const source = ref(null)
  const over = ref(null)

  let touch = null // active touch session

  function clearState() {
    dragging.value = false
    source.value = null
    over.value = null
  }

  function defaultGhost(el, t) {
    const ghost = el.cloneNode(true)
    ghost.style.cssText =
      `position:fixed;left:${t.clientX + ghostOffset.x}px;top:${t.clientY + ghostOffset.y}px;` +
      `z-index:100;pointer-events:none;opacity:0.8;width:${el.offsetWidth}px`
    return ghost
  }

  function detachDocListeners() {
    document.removeEventListener('touchmove', onDocTouchMove)
    document.removeEventListener('touchend', onDocTouchEnd)
    document.removeEventListener('touchcancel', onDocTouchCancel)
  }

  // ── Touch (long-press or instant → drag) ─────────────────
  // `instant` (for dedicated drag handles) engages on touchstart; the default
  // (for rows, where tap/scroll must still work) waits `engageDelay` ms.
  function touchStart(e, from, opts = {}) {
    const { instant = false } = opts
    const t = e.touches[0]
    touch = {
      el: e.currentTarget,
      sx: t.clientX,
      sy: t.clientY,
      engaged: false,
      moved: false,
      ghost: null,
      timer: null,
    }
    source.value = from
    if (instant) {
      engageTouch(t)
    } else {
      touch.timer = setTimeout(() => engageTouch(t), engageDelay)
    }
    document.addEventListener('touchmove', onDocTouchMove, { passive: false })
    document.addEventListener('touchend', onDocTouchEnd)
    document.addEventListener('touchcancel', onDocTouchCancel)
  }

  function engageTouch(t) {
    if (!touch) return
    touch.engaged = true
    let ghost
    if (makeGhost) {
      ghost = makeGhost(touch.el, t)
    } else {
      const el = ghostSource ? ghostSource(touch.el) : touch.el
      ghost = el ? defaultGhost(el, t) : null
    }
    if (ghost) {
      document.body.appendChild(ghost)
      touch.ghost = ghost
    }
    dragging.value = true
    over.value = null
  }

  function onDocTouchMove(e) {
    if (!touch) return
    const t = e.touches[0]
    if (!touch.engaged) {
      if (Math.abs(t.clientX - touch.sx) > slop || Math.abs(t.clientY - touch.sy) > slop) {
        touchCancel()
      }
      return
    }
    if (!touch.moved && (Math.abs(t.clientX - touch.sx) > slop || Math.abs(t.clientY - touch.sy) > slop)) {
      touch.moved = true
    }
    e.preventDefault()
    if (touch.ghost) {
      touch.ghost.style.left = (t.clientX + ghostOffset.x) + 'px'
      touch.ghost.style.top = (t.clientY + ghostOffset.y) + 'px'
    }
    over.value = resolveTarget(document.elementFromPoint(t.clientX, t.clientY))
  }

  function onDocTouchEnd(e) {
    if (!touch) return
    const t = e.changedTouches[0]
    // A drag (not a tap) must have moved past `slop` before it can commit —
    // this keeps an instant handle tap from dropping onto itself.
    if (touch.engaged && touch.moved) {
      const to = resolveTarget(document.elementFromPoint(t.clientX, t.clientY))
      if (to != null && source.value != null) onCommit({ from: source.value, to })
    }
    touchCancel()
  }

  function onDocTouchCancel() {
    touchCancel()
  }

  function touchCancel() {
    if (!touch) return
    clearTimeout(touch.timer)
    if (touch.ghost) touch.ghost.remove()
    touch = null
    detachDocListeners()
    clearState()
  }

  // ── Mouse (HTML5 drag-and-drop) ──────────────────────────
  function dragStart(e, from) {
    // setData is required for Firefox to begin a drag at all.
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', '')
    dragging.value = true
    source.value = from
    over.value = null
  }

  function dragOver(e) {
    if (!dragging.value) return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    over.value = resolveTarget(e.currentTarget)
  }

  function dragLeave() {
    if (dragging.value) over.value = null
  }

  function drop(e) {
    if (!dragging.value) return
    e.preventDefault()
    const to = resolveTarget(e.currentTarget)
    if (to != null && source.value != null) onCommit({ from: source.value, to })
    clearState()
  }

  function dragEnd() {
    clearState()
  }

  onScopeDispose(() => {
    if (touch) touchCancel()
  })

  return { dragging, source, over, touchStart, dragStart, dragOver, dragLeave, drop, dragEnd }
}
