import { ref } from 'vue'

// The panel stack's anchor: the point the 🛠 toggle (closed) and the anchor
// rail (open) sit at, and the point the whole chain derives its position from.
//
// `x`/`y` are the anchor's center in viewport pixels; `null` means "default" —
// the right edge, vertically centered — resolved against the live viewport so
// the default stays glued to the right side on resize. Once dragged, the anchor
// is explicit and is only clamped into the viewport when resolved.
//
// Module singleton: closing and re-opening the stack keeps the anchor where the
// user put it. Floating stacks (Phase 4) will get one anchor each.
const anchor = ref({ x: null, y: null })

// Half the toggle's 42px box horizontally; half the rail's 116px column (three
// 36px buttons + gaps) vertically. Clamping by the rail's half-height keeps the
// whole rail — × and ▾ included — on-screen when the anchor is parked at the
// top or bottom edge (the rail, not the button, is what must stay reachable).
const EDGE_X = 21
const EDGE_Y = 58

function clamp(v, lo, hi) {
  return Math.min(Math.max(v, lo), Math.max(lo, hi))
}

// Where the toggle has always been: `right: 12px`, 42px box, vertically centered.
function defaultAnchor(vw, vh) {
  return { x: vw - 12 - EDGE_X, y: vh / 2 }
}

// The live anchor point, clamped into the viewport.
export function resolveAnchor(vw, vh) {
  const a = anchor.value
  const base = a.x == null ? defaultAnchor(vw, vh) : { x: a.x, y: a.y }
  return { x: clamp(base.x, EDGE_X, vw - EDGE_X), y: clamp(base.y, EDGE_Y, vh - EDGE_Y) }
}

export function setAnchor(x, y) {
  anchor.value = { x, y }
}

export function usePanelAnchor() {
  return { anchor, resolveAnchor, setAnchor }
}
