import { ref } from 'vue'

// The panel stack's anchor: the point the 🛠 toggle (closed) and the anchor
// rail (open) sit at, and the point the whole chain derives its position from.
//
// `x`/`y` are the anchor's center in viewport pixels; `null` means "default" —
// the right edge, vertically centered — resolved against the live viewport so
// the default stays glued to the right side on resize. Once dragged, the anchor
// is explicit and is only clamped into the viewport when resolved. On drop it
// snaps to a viewport edge (see `snapToEdge`), so the button can't be left
// floating in the middle of the screen.
//
// Module singleton: closing and re-opening the stack keeps the anchor where the
// user put it, and the position is remembered per device (localStorage) so it
// survives reloads. Floating stacks (Phase 4) will get one anchor each.
const STORAGE_KEY = 'gmPanelAnchor'

// Only the explicit position is stored — the default spot (null) is resolved
// from the live viewport, so it never needs persisting. Anything unreadable or
// out of shape falls back to the default; `resolveAnchor` clamps stale
// coordinates (e.g. saved on a larger screen) into the current viewport.
function loadAnchor() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { x: null, y: null }
    const parsed = JSON.parse(raw)
    return {
      x: Number.isFinite(parsed?.x) ? parsed.x : null,
      y: Number.isFinite(parsed?.y) ? parsed.y : null,
    }
  } catch {
    return { x: null, y: null }
  }
}

const anchor = ref(loadAnchor())

// Which way the chain opens. Derived from the anchor's edge, and only updated
// while the anchor is inside an edge band — away from every edge it keeps the
// direction the stack already had.
const direction = ref('left')

// Half the toggle's 42px box horizontally; half the rail's 116px column (three
// 36px buttons + gaps) vertically. Clamping by the rail's half-height keeps the
// whole rail — × and ▾ included — on-screen when the anchor is parked at the
// top or bottom edge (the rail, not the button, is what must stay reachable).
const EDGE_X = 21
const EDGE_Y = 58

// The band (fraction of the viewport, per axis) inside which an edge claims the
// anchor — for the direction and for the drop snap alike.
const BAND = 0.2

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

// The viewport edge the anchor belongs to (within the band), or null when it is
// away from every edge. Candidates are ranked by normalized distance; ties
// prefer right → left → bottom → top (the scan order, with strict `<`).
export function edgeOf(x, y, vw, vh) {
  const candidates = [
    ['right', (vw - x) / vw],
    ['left', x / vw],
    ['bottom', (vh - y) / vh],
    ['top', y / vh],
  ]
  let best = null
  let bestDist = Infinity
  for (const [name, dist] of candidates) {
    if (dist <= BAND && dist < bestDist) {
      best = name
      bestDist = dist
    }
  }
  return best
}

// Direction for an anchor position — or null, meaning "keep the current one".
// A vertical chain opens downwards from a top-edge anchor and upwards from a
// bottom-edge anchor.
export function deriveDirection(x, y, vw, vh) {
  const edge = edgeOf(x, y, vw, vh)
  if (edge === 'right') return 'left'
  if (edge === 'left') return 'right'
  if (edge === 'top') return 'down'
  if (edge === 'bottom') return 'up'
  return null
}

// Drop snap: the anchor comes to rest on the nearest viewport edge (normalized
// distance, ties preferring right → left → bottom → top), keeping its position
// along that edge. Being pinned to an edge is also what makes the direction
// unambiguous at rest.
export function snapToEdge(x, y, vw, vh) {
  let target = edgeOf(x, y, vw, vh)
  if (!target) {
    const candidates = [
      ['right', (vw - x) / vw],
      ['left', x / vw],
      ['bottom', (vh - y) / vh],
      ['top', y / vh],
    ]
    let bestDist = Infinity
    for (const [name, dist] of candidates) {
      if (dist < bestDist) {
        target = name
        bestDist = dist
      }
    }
  }
  const out = { x, y }
  if (target === 'right') out.x = vw - EDGE_X
  else if (target === 'left') out.x = EDGE_X
  else if (target === 'bottom') out.y = vh - EDGE_Y
  else out.y = EDGE_Y
  return out
}

export function setAnchor(x, y) {
  anchor.value = { x, y }
  persistAnchor()
}

// Debounced so a drag writes once (per move would write on every pointermove).
let persistTimer = null
function persistAnchor() {
  clearTimeout(persistTimer)
  persistTimer = setTimeout(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(anchor.value))
    } catch {
      // Storage unavailable (private mode, quota) — the anchor still works this
      // session, it just won't be remembered.
    }
  }, 250)
}

export function usePanelAnchor() {
  return { anchor, direction, resolveAnchor, deriveDirection, snapToEdge, setAnchor }
}
