import { ref, markRaw } from 'vue'

// Window-manager registry for GM panels.
//
// A "window" is a top-level panel unit — the thing that can be collapsed,
// docked, or (later) floated independently. The seeded root window stays
// reactive via PanelStack's `rootPanel` prop; `windows` holds the additional
// top-level windows (opened outside the hierarchy, or detached).
//
// Each window keeps layout state so collapse/dock and future free-float share
// one source of truth:
//   { id, spec, dock, collapsed, x, y, z }
//
// `spec` is the same shape used everywhere: `{ component, title, id, props, listeners }`.

const windows = ref([])
let seq = 0

function normalizeSpec(spec) {
  // markRaw the component so Vue doesn't try to make the definition reactive
  // (avoids the "Component made reactive" warning). Mirrors Panel.vue.
  return { ...spec, component: markRaw(spec.component) }
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
      z: windows.value.length,
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

export function usePanelWindows() {
  return { windows, spawn, close, replace, toggleCollapse, setDock, move, setDirection }
}
