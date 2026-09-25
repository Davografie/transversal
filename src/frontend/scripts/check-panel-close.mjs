/**
 * Executable check for the location tree's follow-the-open-panel highlight
 * (P7.18).
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-panel-close.mjs
 *
 * The report: "The location tree should track which child panel is open, and if
 * the child panel closes the tree should update accordingly. Now it happens that
 * no child panels are open but the tree highlights an item and believes it to be
 * open."
 *
 * The tree's highlight is `selectedId`, which `toggleEntity` sets and only ever
 * clears on a *second click on the same row*. A panel closed by its own × (or a
 * chip, or Esc) never routes back through it, so the row stayed lit — and the
 * next click on that row read as "already open" and closed a panel that was
 * already gone.
 *
 * The panel now reports its own closes. The subtle half is that **detaching is
 * not a close**: `detachChild` drops the child into a floating window, where it
 * is still open and still registered under its own identity, so a detached
 * panel must keep its row lit. Both branches are executed below, from the
 * shipping source, rather than asserted about.
 */
import { readFileSync } from 'node:fs'
import { ref } from 'vue'

import { usePanel } from '../src/composables/usePanel.js'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}

const PANEL = readFileSync(new URL('../src/components/gm/Panel.vue', import.meta.url), 'utf8')
const GM = readFileSync(new URL('../src/components/GmPanel.vue', import.meta.url), 'utf8')

/** The shipped text of one top-level function, so it runs as written. */
function lift(src, signature) {
  const i = src.indexOf(signature)
  if (i < 0) throw new Error(`not found: ${signature}`)
  const end = src.indexOf('\n}', i)
  return src.slice(i, end + 2)
}

// ── 1. the panel's close signal ──────────────────────────────────────────
console.log('\nPanel.vue — a child close is reported\n')

{
  const src = lift(PANEL, 'function onChildClose(fn) {') + '\n' +
              lift(PANEL, 'function closeChild(key) {')
  const make = new Function('children', 'activeKey', 'childCloseListeners', 'panelLog',
    src + '\nreturn { onChildClose, closeChild }')
  const children = ref([
    { key: 'c1', spec: { component: 'A', id: 'e1' } },
    { key: 'c2', spec: { component: 'B', id: 'e2' } },
  ])
  const activeKey = ref('c2')
  const listeners = new Set()
  const { onChildClose, closeChild } = make(children, activeKey, listeners, () => {})

  const heard = []
  const off = onChildClose((spec) => heard.push(spec.id))

  closeChild('c1')
  ok('closing a child reports its spec', heard, ['e1'])
  ok('and removes it', children.value.map((c) => c.key), ['c2'])
  ok('the active child is left alone when it was not the one closed', activeKey.value, 'c2')

  closeChild('c2')
  ok('closing the active child reassigns it to the new last', activeKey.value, null)
  ok('and reports that one too', heard, ['e1', 'e2'])

  closeChild()
  ok('closing with no key removes nothing when there are no children', children.value.length, 0)
  ok('and reports nothing, rather than reporting undefined', heard, ['e1', 'e2'])

  closeChild('c1')
  ok('closing an unknown key reports nothing', heard, ['e1', 'e2'])
}

{
  // Several listeners, and the unsubscribe.
  const src = lift(PANEL, 'function onChildClose(fn) {') + '\n' +
              lift(PANEL, 'function closeChild(key) {')
  const make = new Function('children', 'activeKey', 'childCloseListeners', 'panelLog',
    src + '\nreturn { onChildClose, closeChild }')
  const children = ref([{ key: 'c1', spec: { component: 'A', id: 'e1' } }])
  const listeners = new Set()
  const { onChildClose, closeChild } = make(children, ref('c1'), listeners, () => {})

  const a = [], b = []
  const offA = onChildClose((s) => a.push(s.id))
  onChildClose((s) => b.push(s.id))
  children.value = [{ key: 'c1', spec: { component: 'A', id: 'e1' } }]
  closeChild('c1')
  ok('every listener hears it', [a, b], [['e1'], ['e1']])

  children.value = [{ key: 'c3', spec: { component: 'A', id: 'e3' } }]
  offA()
  closeChild('c3')
  ok('an unsubscribed listener goes quiet', [a, b], [['e1'], ['e1', 'e3']])
  ok('the unsubscribe is a function', typeof offA, 'function')
}

// ── 2. detaching is NOT a close ──────────────────────────────────────────
console.log('\ndetaching a child into a floating window\n')

{
  const src = lift(PANEL, 'function detachChild(key, point) {')
  // `panelLog` is the only other free name. `childCloseListeners` is deliberately
  // NOT a parameter: if `detachChild` grew a notify call it would throw here,
  // which is the point of the case.
  const make = new Function('children', 'activeKey', 'spawnWindow', 'panelIdentityKey', 'props', 'panelLog',
    src + '\nreturn detachChild')
  const children = ref([{ key: 'c1', spec: { component: 'A', id: 'e1' } }])
  const activeKey = ref('c1')
  const spawned = []
  const detachChild = make(
    children, activeKey,
    (spec) => spawned.push(spec),
    () => 'SomePanel:root',
    { spec: { component: 'Root', id: 'root' } },
    () => {},
  )
  detachChild('c1', { x: 1, y: 2, direction: 'left' })
  ok('the child leaves the stack', children.value, [])
  ok('it was handed to a floating window instead', spawned.map((s) => s.id), ['e1'])
  ok('the active child moves to the new last', activeKey.value, null)
  ok('and no close is reported — a detached panel is still open',
    /function detachChild[\s\S]*?\n\}/.test(PANEL) &&
    !/function detachChild[\s\S]*?\n\}/.exec(PANEL)[0].includes('childCloseListeners'), true)
  ok('the panel registers itself as the window\'s parent',
    PANEL.includes('sourceParentKey: panelIdentityKey(props.spec?.component, props.spec?.id)'), true)
}

// ── 3. the wiring exists (a signal nothing subscribes to is the bug) ─────
console.log('\nthe signal is actually connected\n')

ok('Panel.vue provides it to its slot content', /provide\(panelKey, \{[\s\S]*?onChildClose,/.test(PANEL), true)
ok('GmPanel subscribes on mount', /offChildClose = panel\.onChildClose\(onPanelChildClose\)/.test(GM), true)
ok('and unsubscribes on unmount', /if \(offChildClose\) offChildClose\(\)/.test(GM), true)
ok('the no-op panel answers it too, so a panel-less render cannot throw',
  typeof usePanel().onChildClose(() => {}), 'function')

// ── 4. GmPanel's response, executed ──────────────────────────────────────
console.log('\nGmPanel — what a close clears\n')

{
  const src = lift(GM, 'function onPanelChildClose(spec) {')
  const make = new Function('GmEntityEditPanel', 'selectedId', 'editing', 'selected',
    src + '\nreturn onPanelChildClose')
  const EditPanel = { __name: 'GmEntityEditPanel' }
  const onPanelChildClose = make(EditPanel, ref('e1'), ref(true), ref({ id: 'e1', name: 'Craigmuir' }))

  // A different component's panel closing leaves the tree alone.
  const state = { selectedId: ref('e1'), editing: ref(true), selected: ref({ id: 'e1', name: 'Craigmuir' }) }
  const run = make(EditPanel, state.selectedId, state.editing, state.selected)
  run({ component: { __name: 'GmTraitsetsPanel' }, id: 'e1' })
  ok('another panel closing does not clear the tree', state.selectedId.value, 'e1')

  // A different entity's panel closing leaves this selection alone.
  run({ component: EditPanel, id: 'e2' })
  ok('a different entity\'s panel closing does not clear it', state.selectedId.value, 'e1')

  // The selection's own panel closing clears it — the reported bug.
  run({ component: EditPanel, id: 'e1' })
  ok('the selected entity\'s panel closing clears the highlight', state.selectedId.value, null)
  ok('and the selection with it', [state.editing.value, state.selected.value], [false, null])

  // An id-less spec cannot be the selected entity's panel, so it must not clear.
  const idless = { selectedId: ref('e9'), editing: ref(true), selected: ref({ id: 'e9' }) }
  const runIdless = make(EditPanel, idless.selectedId, idless.editing, idless.selected)
  runIdless({ component: EditPanel })
  ok('a spec with no id does not clear a real selection',
    [idless.selectedId.value, idless.editing.value], ['e9', true])
}

// ── 5. the highlight is driven by selectedId ─────────────────────────────
console.log('\nthe tree reads the state this fixes\n')

ok('the tree takes its highlight from selectedId',
  /:selected-id="selectedId"/.test(GM), true)
ok('the factions list takes it from the same value',
  /:selected-ids="selectedId \? \[selectedId\] : \[\]"/.test(GM), true)
ok('a second click on the lit row still closes its own panel',
  /if \(editing\.value && selectedId\.value === e\.id\) \{[\s\S]*?panel\.closeChild\(\)/.test(GM), true)

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
