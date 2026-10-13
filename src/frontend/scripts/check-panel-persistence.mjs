/**
 * Executable check for persistent floating GM panels.
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image, the same
 * way as the other checks:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-panel-persistence.mjs
 *
 * The request: "I want floating GM panels persistent client-side."
 *
 * A window is `{ id, spec, dock, collapsed, x, y, direction, sourceParentKey, z }`
 * and its spec is `{ component, title, id, props, listeners, context, badge }`.
 * The component is a Vue object and the listeners/context are closures and live
 * instances — **nothing that survives JSON** — so a window is stored as a
 * registry name + props + geometry and rebuilt from
 * `constants/restorablePanels.js` on load. That registry is a short allow-list
 * because a restored window has no listeners and no context, so only panels whose
 * whole spec is props may come back.
 *
 * The rules live in `panelWindowPersistence.js`, which imports nothing, so they
 * run here directly rather than being restated.
 */
import { readFileSync } from 'node:fs'
import { reactive, readonly, ref } from 'vue'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}

const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8')
const { serializeWindow, serializeWindows, deserializeWindows, propsAreStorable } =
  await import('../src/composables/panelWindowPersistence.js')

const REGISTRY = read('../src/constants/restorablePanels.js')
const WINDOWS = read('../src/composables/usePanelWindows.js')

// The shipped `restorableNameOf`, lifted out of the registry module — which
// imports ten `.vue` files and so cannot be imported here. Its body is one small
// function over `RESTORABLE_PANELS`, which is passed in.
function between(src, from, to) {
  const i = src.indexOf(from)
  if (i < 0) throw new Error(`not found: ${from}`)
  const j = src.indexOf(to, i)
  if (j < 0) throw new Error(`not found: ${to}`)
  return src.slice(i, j)
}

const COMP = { name: 'GmEntityEditPanel' }
const OTHER = { name: 'GmTraitEditPanel' }
const nameOf = (c) => (c === COMP ? 'GmEntityEditPanel' : c === OTHER ? 'GmTraitEditPanel' : null)

const REGISTRY_OBJECT = { GmEntityEditPanel: COMP, GmTraitEditPanel: OTHER }
const restorableNameOf = new Function('RESTORABLE_PANELS',
  `${between(REGISTRY, 'export function restorableNameOf(', '\nexport function restorableComponent')
    .replace('export function', 'function')}
   return restorableNameOf`)(REGISTRY_OBJECT)
const win = (spec, layout = {}) => ({
  id: 'gm-win-1',
  spec,
  dock: 'right',
  collapsed: false,
  x: 120,
  y: 80,
  direction: 'left',
  sourceParentKey: 'GmPanel:',
  z: 3,
  ...layout,
})

// ── 1. what may be stored ───────────────────────────────────────────────
console.log('\nwhat a window may carry into storage\n')

{
  const rec = serializeWindow(win({
    component: COMP,
    title: 'Pine Ridge',
    id: 'loc-1',
    badge: 'LOCATION',
    props: { entityId: 'loc-1', currentLocationId: 'loc-2' },
    listeners: { saved: () => {} },
    context: { entityEditor: { some: 'instance' } },
  }), nameOf)

  ok('an allow-listed panel is stored', !!rec, true)
  ok('by registry name, not by component object', rec.name, 'GmEntityEditPanel')
  ok('with its props', rec.props, { entityId: 'loc-1', currentLocationId: 'loc-2' })
  ok('and its identity for the header', [rec.title, rec.specId, rec.badge], ['Pine Ridge', 'loc-1', 'LOCATION'])
  ok('and its geometry', [rec.x, rec.y, rec.direction, rec.dock, rec.collapsed, rec.sourceParentKey, rec.z],
    [120, 80, 'left', 'right', false, 'GmPanel:', 3])
  ok('listeners are never written', Object.keys(rec).includes('listeners'), false)
  ok('context is never written', Object.keys(rec).includes('context'), false)
  ok('the component object is never written', JSON.stringify(rec).includes('GmEntityEditPanel"'), true)
  ok('and the record survives a real JSON round trip',
    JSON.parse(JSON.stringify(rec)).props, { entityId: 'loc-1', currentLocationId: 'loc-2' })
}

{
  ok('a panel that is not in the registry is not stored',
    serializeWindow(win({ component: { name: 'GmUnknown' }, props: {} }), nameOf), null)
  ok('a window with no spec is not stored', serializeWindow({ id: 'x' }, nameOf), null)
}

// ── 2. the props safety net ─────────────────────────────────────────────
console.log('\nprops that would restore wrong are refused\n')

ok('plain data is fine', propsAreStorable({ a: 1, b: 'x', c: null, d: [1, { e: true }] }), true)
ok('a function is not', propsAreStorable({ onChange: () => {} }), false)
ok('a real ref is not — it would serialize to its guts',
  propsAreStorable({ draft: ref(1) }), false)
ok('a nested ref is not either', propsAreStorable({ a: { b: ref('x') } }), false)
ok('a real class instance is not — it would come back a plain object',
  propsAreStorable({ editor: new (class { constructor() { this.x = 1 } })() }), false)
ok('a nested function is not', propsAreStorable({ nested: { deep: { fn: () => {} } } }), false)
ok('an array of functions is not', propsAreStorable({ list: [() => {}] }), false)
ok('and such a window is refused rather than stored broken',
  serializeWindow(win({ component: COMP, props: { onSave: () => {} } }), nameOf), null)
ok('a window with no props is storable', !!serializeWindow(win({ component: COMP }), nameOf), true)

// A reactive proxy is only *decorated*, so it is snapshotted rather than refused.
// This is not a nicety: the SFX editor is opened with a record straight out of the
// shared store, so its props are proxies by construction — refusing them is what
// made it unrestorable.
{
  const sfx = reactive({ id: 'sfx-reveal-entity', name: 'Reveal Entity', trigger: 'manual' })
  ok('a reactive prop is storable', propsAreStorable({ sfx }), true)
  const rec = serializeWindow(win({ component: COMP, props: { sfx, owner: { ownerType: 'LOCATION', ownerId: 'loc-1' } } }), nameOf)
  ok('and it is snapshotted as plain data, not internals',
    JSON.parse(JSON.stringify(rec)).props, { sfx: { id: 'sfx-reveal-entity', name: 'Reveal Entity', trigger: 'manual' }, owner: { ownerType: 'LOCATION', ownerId: 'loc-1' } })
  ok('a readonly proxy is snapshotted too', propsAreStorable({ x: readonly(reactive({ n: 1 })) }), true)
  // …but a ref *inside* a reactive object is still a live handle.
  ok('a ref nested in a reactive object is still refused',
    propsAreStorable({ obj: reactive({ inner: ref(1) }) }), false)
}

// ── 2b. finding a panel's registry name ─────────────────────────────────
// This is the bug the first cut shipped, and it is why detached panels vanished
// on refresh: the Vite dev server serves a module it has invalidated (HMR) under
// `<path>?t=<stamp>`, so the same SFC can exist as two objects — the one the
// opener passed and the one the registry holds. Identity alone missed it, the
// window serialized to nothing, and the store was then rewritten empty.
console.log('\nwhich registry name a component gets\n')

ok('an identity match resolves', restorableNameOf(COMP), 'GmEntityEditPanel')
const lookalike = { __name: 'GmEntityEditPanel' }   // a second module instance
ok('a second instance of the same SFC resolves, by __name',
  restorableNameOf(lookalike), 'GmEntityEditPanel')
ok('a component the registry does not hold is not named',
  restorableNameOf({ __name: 'GmUnknown' }), null)
ok('no component is no name', restorableNameOf(null), null)
ok('a component with neither identity nor name is not named',
  restorableNameOf({}), null)

const preFixNameOf = (reg, c) => {
  for (const [n, x] of Object.entries(reg)) if (x === c) return n
  return null
}
ok('pre-fix: identity alone missed the second instance', preFixNameOf(REGISTRY_OBJECT, lookalike), null)
ok('shipped: the same component resolves', restorableNameOf(lookalike), 'GmEntityEditPanel')

// ── 3. restoring ────────────────────────────────────────────────────────
console.log('\nrestoring a stored window\n')

const lookup = (name) => (name === 'GmEntityEditPanel' ? COMP : name === 'GmTraitEditPanel' ? OTHER : null)

{
  const stored = serializeWindows([
    win({ component: COMP, title: 'A', id: 'a', props: { entityId: 'a' } }, { x: 10, y: 20 }),
    win({ component: OTHER, title: 'B', id: 'b', props: { traitId: 't' } }, { x: 30, y: 40 }),
    win({ component: { name: 'Gone' }, title: 'C', props: {} }),          // not in the registry
    win({ component: COMP, title: 'D', props: { f: () => {} } }),         // props not storable
  ], nameOf)
  ok('only the two restorable windows are written', stored.length, 2)

  const back = deserializeWindows(stored, lookup)
  ok('both come back', back.length, 2)
  ok('with the same components', back.map((w) => w.spec.component.name), ['GmEntityEditPanel', 'GmTraitEditPanel'])
  ok('and the same props', back.map((w) => w.spec.props), [{ entityId: 'a' }, { traitId: 't' }])
  ok('and the same positions', back.map((w) => [w.x, w.y]), [[10, 20], [30, 40]])
  ok('a restored spec carries no listeners', back.every((w) => !('listeners' in w.spec)), true)
  ok('and no context', back.every((w) => !('context' in w.spec)), true)
  ok('the session id is not restored — the caller assigns a fresh one',
    back.every((w) => !('id' in w)), true)
}

{
  ok('a name that no longer resolves is dropped', deserializeWindows(
    [{ name: 'RenamedAway', props: {} }, { name: 'GmEntityEditPanel', props: {} }], lookup).length, 1)
  ok('garbage storage restores nothing', deserializeWindows({ not: 'an array' }, lookup), [])
  ok('null restores nothing', deserializeWindows(null, lookup), [])
  ok('a record with no props still restores its panel',
    deserializeWindows([{ name: 'GmEntityEditPanel' }], lookup)[0].spec.props, {})
}

// ── 3b. the collapsed chip state ────────────────────────────────────────
// A Panel's collapse is `props.collapsed ?? localCollapsed` (Panel.vue): pass the
// prop and the state is the caller's, leave it off and the Panel keeps it to
// itself — which is why a reload always came back expanded. These are the two
// places a *root* panel is rendered, and both now pass it.
console.log('\na panel\'s collapsed state is the caller\'s, and is stored\n')

{
  const stored = serializeWindows(
    [win({ component: COMP, props: {} }, { collapsed: true, dock: 'left', direction: 'up' })], nameOf)
  ok('a collapsed window stores that', stored[0].collapsed, true)
  ok('and the dock and direction beside it', [stored[0].dock, stored[0].direction], ['left', 'up'])
  const back = deserializeWindows(stored, lookup)
  ok('and it comes back collapsed', back[0].collapsed, true)
  ok('an expanded one stays expanded',
    deserializeWindows(serializeWindows([win({ component: COMP, props: {} })], nameOf), lookup)[0].collapsed, false)
}

const PANEL = read('../src/components/gm/Panel.vue')
const WINDOW = read('../src/components/gm/PanelWindow.vue')
const STACK = read('../src/components/gm/PanelStack.vue')

ok('a Panel with no `collapsed` prop keeps the state locally — the reason it was lost',
  /props\.collapsed \?\? localCollapsed\.value/.test(PANEL), true)
ok('a floating window passes its registry field in', /:collapsed="!!win\.collapsed"/.test(WINDOW), true)
ok('and routes the toggle back to the registry', /@toggle-collapse="toggleCollapsed"/.test(WINDOW)
  && /toggleCollapse\(props\.win\.id\)/.test(WINDOW), true)
ok('the stack root passes its own persisted ref in', /:collapsed="rootCollapsed"/.test(STACK), true)
ok('and writes the toggle back', /@toggle-collapse="rootCollapsed = !rootCollapsed"/.test(STACK), true)
ok('through the write-through storage helper, keyed per device',
  /usePersistedRef\('gmPanelStackCollapsed', false\)/.test(STACK), true)

// ── 4. the wiring ───────────────────────────────────────────────────────
console.log('\nthe registry is an allow-list, and the store is wired\n')

for (const name of ['GmEntityEditPanel', 'GmTraitEditPanel', 'GmTraitsetDetail', 'GmSfxEditPanel',
  'GmRollTableEditPanel', 'GmRollTableEntryEditPanel',
  'GmLifePathDetailPanel', 'GmPortalConfigPanel', 'GmTraitInstancesPanel', 'ImageViewer']) {
  ok(`${name} is restorable`, new RegExp(`^\\s*${name},$`, 'm').test(REGISTRY), true)
}

// Each of these edits a draft handed to it through the spec's `context`, so a
// restored copy would either do nothing or edit the wrong thing.
for (const name of ['GmDisplayNameEditPanel', 'GmEffectEditPanel', 'GmProjectionEditPanel',
  'GmPathEditPanel', 'GmRollTableEntryEffectPanel', 'GmEntityCreatePanel']) {
  ok(`${name} is NOT restorable`, new RegExp(`^\\s*${name},$`, 'm').test(REGISTRY), false)
}

ok('the store uses its own storage key',
  /WINDOW_STORAGE_KEY/.test(WINDOWS) && /'gmPanelWindows'/.test(read('../src/composables/panelWindowPersistence.js')), true)
ok('windows are restored when the module loads', /windows\.value = loadStoredWindows\(\)/.test(WINDOWS), true)
ok('and written back on change', /watch\(windows, scheduleSave, \{ deep: true \}\)/.test(WINDOWS), true)
ok('the write is debounced, because a drag fires every frame', /setTimeout\(saveStoredWindows, 250\)/.test(WINDOWS), true)
ok('and flushed on pagehide, so a reload cannot lose the last drag',
  /addEventListener\('pagehide'/.test(WINDOWS), true)

console.log(`\n${pass} passed, ${fail} failed\n`)
process.exit(fail ? 1 : 0)
