import { ref, watch, markRaw } from 'vue'
import { restorableNameOf, restorableComponent } from '@/constants/restorablePanels.js'
import {
  WINDOW_STORAGE_KEY,
  serializeWindows,
  deserializeWindows,
} from './panelWindowPersistence.js'

// Window-manager registry for GM panels.
//
// A "window" is a top-level panel unit — the thing that can be collapsed,
// docked, or (later) floated independently. The seeded root window stays
// reactive via PanelStack's `rootPanel` prop; `windows` holds the additional
// top-level windows (opened outside the hierarchy, or detached).
//
// Each window keeps layout state so collapse/dock and future free-float share
// one source of truth:
//   { id, spec, dock, collapsed, x, y, direction, sourceParentKey, z }
//
// `z` is a **stacking rank**, not a pixel value: the unit holding the highest
// rank paints on top (see *Stacking* below). The windows are remembered per
// device — see *Persistence* below.

// The stack root's unit id. The chain is not a window — its spec is a prop of
// PanelStack — so it has no record to keep its rank in.
const ROOT_ID = 'root'

const windows = ref([])
let seq = 0

// The highest rank handed out so far. Ranks are handed out one at a time and
// never reused, so "the top" is simply "the highest rank" and raising is a bump.
// It is re-derived from the restored windows on load, or a window spawned after a
// reload would be ranked underneath the ones that came back.
let zSeq = 0

// The chain's own rank, beside the counter for the same reason.
const rootZ = ref(0)

function normalizeSpec(spec) {
  // markRaw the component so Vue doesn't try to make the definition reactive
  // (avoids the "Component made reactive" warning). Mirrors Panel.vue.
  return { ...spec, component: markRaw(spec.component) }
}

// ── Persistence (per device) ──────────────────────────
// Floating windows are client state — they belong to this screen, not to the
// campaign — so they are remembered in `localStorage` beside the panel anchor
// (`gmPanelAnchor`), not on the server. Only windows whose panel is in the
// registry and whose props survive JSON are stored; `panelWindowPersistence.js`
// explains why a spec cannot be stored whole.
//
// A restored window comes back **without** `listeners`/`context`: it shows its
// record and edits it, but the opener's reactions — refreshing the gallery behind
// an image, re-reading the tree after a save — do not fire, because the closure
// that would do it went with the page. That is why the registry is a short
// allow-list rather than every panel.
function loadStoredWindows() {
  if (typeof localStorage === 'undefined') return []
  try {
    const raw = localStorage.getItem(WINDOW_STORAGE_KEY)
    if (!raw) return []
    const restored = deserializeWindows(JSON.parse(raw), (name) => {
      const c = restorableComponent(name)
      return c ? markRaw(c) : null
    })
    // Fresh per-session handles: nothing outside the registry refers to them.
    restored.forEach((w) => { w.id = `gm-win-${++seq}` })
    // `deserializeWindows` renormalises the restored ranks into a dense run, so
    // the highest one is where the next rank starts.
    zSeq = restored.reduce((max, w) => Math.max(max, w.z), 0)
    return restored
  } catch {
    return []
  }
}

function saveStoredWindows() {
  try {
    localStorage.setItem(
      WINDOW_STORAGE_KEY,
      JSON.stringify(serializeWindows(windows.value, restorableNameOf)),
    )
  } catch {}
}

windows.value = loadStoredWindows()

// Debounced like the anchor's write: a drag moves a window on every frame, and
// only the resting place is worth storing.
let saveTimer = null
function scheduleSave() {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(saveStoredWindows, 250)
}
watch(windows, scheduleSave, { deep: true })

// Belt and braces, as with `usePersistedRef`: a window dragged and then lost to a
// reload must not lose its last position to the debounce.
if (typeof window !== 'undefined') {
  window.addEventListener('pagehide', () => {
    clearTimeout(saveTimer)
    saveStoredWindows()
  })
}

function spawn(spec, opts = {}) {
  const id = opts.id ?? `gm-win-${++seq}`
  windows.value = [
    ...windows.value,
    {
      id,
      spec: normalizeSpec(spec),
      dock: opts.dock ?? 'right',
      collapsed: opts.collapsed ?? false,
      x: opts.x ?? null,
      y: opts.y ?? null,
      // Which way this window's chain opens. Fixed at spawn: a floating window
      // is free-standing, so it never re-derives from an edge the way the main
      // stack's anchor does.
      direction: opts.direction ?? 'left',
      // What the window's parent *was* — a panel identity key (`component:id`).
      // Dock-back looks up a live panel with that identity, so a parent that was
      // closed and re-opened accepts the window again.
      sourceParentKey: opts.sourceParentKey ?? null,
      // A new window lands on top — it was just opened, and a detach parks it
      // exactly where the panel it came from still is.
      z: ++zSeq,
    },
  ]
  return id
}

function close(id) {
  windows.value = windows.value.filter((w) => w.id !== id)
}

function replace(id, spec) {
  const w = windows.value.find((w) => w.id === id)
  if (w) w.spec = normalizeSpec(spec)
}

function toggleCollapse(id) {
  const w = windows.value.find((w) => w.id === id)
  if (w) w.collapsed = !w.collapsed
}

function setDock(id, dock) {
  const w = windows.value.find((w) => w.id === id)
  if (w) w.dock = dock
}

function move(id, x, y) {
  const w = windows.value.find((w) => w.id === id)
  if (w) {
    w.x = x
    w.y = y
  }
}

// Which way this window's chain opens. Derived from the window's own anchor
// (same edge bands + keep-last rule as the main stack), so a floating window
// reorients as it is moved — independently of the root stack.
function setDirection(id, direction) {
  const w = windows.value.find((w) => w.id === id)
  if (w && w.direction !== direction) w.direction = direction
}

// ── Stacking (dynamic z-index) ────────────────────────
// Clicking anywhere in a panel raises its whole **unit** — the chain, or one
// floating window — above every other unit. Unit, not panel: a unit is one
// chain whose panels are laid out side by side, so the thing you clicked to
// bring forward is the chain. Two units genuinely do overlap — a detached
// window parks exactly where its panel was — which is what this orders.
//
// The rank is applied to the unit's wrapper in PanelStack, and that wrapper is a
// stacking context, so ranks are local to the panel layer: the units reorder
// freely among themselves while the layer stays under the 🛠 toggle (26) and
// under every modal, however often you click.
function raise(id) {
  if (!id) return
  if (id === ROOT_ID) {
    // Already the top — don't burn a rank (and a storage write) on a no-op.
    if (rootZ.value < zSeq) rootZ.value = ++zSeq
    return
  }
  const w = windows.value.find((x) => x.id === id)
  if (w && w.z < zSeq) w.z = ++zSeq
}

export function usePanelWindows() {
  return { windows, spawn, close, replace, toggleCollapse, setDock, move, setDirection, raise, rootZ }
}
