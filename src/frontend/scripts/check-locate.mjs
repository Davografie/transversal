/**
 * Executable check for the tree's Locate action (⊙, and the recenter after the
 * last focus chip is removed).
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-locate.mjs
 *
 * Two things were wrong with it, both reported from live testing:
 *
 *  1. **It centered a collapsed chevron.** In the plain (acting-entity) view
 *     locations default closed, and `scrollToNode` expanded only the *ancestor
 *     chain* — never the target — so the jump showed the current location's
 *     chevron and none of its children.
 *  2. **It centered, full stop.** Even expanded, 'center' splits the room between
 *     what is above and what is below, so the children were the half that fell
 *     off. Locate now parks the row a couple of rows below the scrollport top,
 *     which keeps the location in context and gives its children the room.
 *
 * The App-side functions are extracted from the shipped `GmPanel.vue` text and
 * executed against a fake scroller, so the check can only pass if the real
 * arithmetic is right. `findAncestorIds` (the shipped `useLocationTree`) is
 * exercised for real, and the expansion is asserted on the real ref.
 */
import { readFileSync } from 'node:fs'
import { ref, nextTick } from 'vue'
import { useLocationTree } from '../src/composables/useLocationTree.js'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}

const PANEL = 'src/components/GmPanel.vue'
const script = readFileSync(PANEL, 'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1]
const scrollBody = script.match(/function scrollLocationIntoView\(locationId, \{ align = 'center' \} = \{\}\) \{([\s\S]*?)\n\}/)[1]
const locateBody = script.match(/function scrollToNode\(nodeId\) \{([\s\S]*?)\n\}/)[1]

// The shipped text, run with a stubbed document. `nextTick` is Vue's real one,
// so the deferred scroll runs in the same order it does in the app.
const compile = (document) => new Function('deps', `
  const { expandedNodes, locationTree, findAncestorIds, nextTick, document } = deps
  function scrollLocationIntoView(locationId, { align = 'center' } = {}) { ${scrollBody} }
  function scrollToNode(nodeId) { ${locateBody} }
  return { scrollLocationIntoView, scrollToNode }
`)({ expandedNodes: TREE.expandedNodes, locationTree: TREE.locationTree, findAncestorIds: TREE.findAncestorIds, nextTick, document })

// A location two levels down, with children of its own.
const NODES = [{ id: 'u1', name: 'Earth', children: [{ id: 'a', name: 'Asia', children: [{ id: 'cur', name: 'Krasnoyarsk-45', children: [{ id: 'kid', name: 'Willow Bath' }] }] }] }]
const TREE = useLocationTree({ filteredEntities: ref([]), activeFilters: ref([]), currentUniverse: ref('earth') })
TREE.locationTree.value = NODES

/** A fake row inside a fake `.browse-zone` scroller. */
function dom({ rowTop = 500, zoneTop = 100, scrollTop = 1000, rowH = 32, hasZone = true } = {}) {
  const scrolled = [], intoView = []
  const zone = hasZone ? {
    scrollTop,
    getBoundingClientRect: () => ({ top: zoneTop }),
    scrollTo: (o) => scrolled.push(o),
  } : null
  const row = {
    offsetHeight: rowH,
    getBoundingClientRect: () => ({ top: rowTop }),
    closest: () => zone,
    scrollIntoView: (o) => intoView.push(o),
  }
  return { document: { querySelector: () => row }, scrolled, intoView }
}

// ── 1. Locate expands the target, not just its ancestors ─────────────────
console.log('\nLocate — expansion\n')

TREE.expandedNodes.value = {}
{
  const d = dom()
  compile(d.document).scrollToNode('cur')
  await nextTick()
  ok('the ancestor chain opens', [!!TREE.expandedNodes.value.u1, !!TREE.expandedNodes.value.a], [true, true])
  ok('the current location itself opens (was left collapsed)', TREE.expandedNodes.value.cur, true)
  ok('the scroll still happens', d.scrolled.length, 1)
}

TREE.expandedNodes.value = {}
{
  const d = dom()
  compile(d.document).scrollToNode('')
  await nextTick()
  ok('an empty id touches nothing', [TREE.expandedNodes.value, d.scrolled.length], [{}, 0])
}

TREE.expandedNodes.value = {}
{
  const d = dom()
  compile(d.document).scrollToNode('not-in-the-tree')
  await nextTick()
  ok('an off-tree id expands nothing but still scrolls', [TREE.expandedNodes.value, d.scrolled.length], [{}, 1])
}

// ── 2. alignment: a couple of rows of context, children below ────────────
console.log('\nLocate — alignment\n')

{
  const d = dom({ rowTop: 500, zoneTop: 100, scrollTop: 1000, rowH: 32 })
  compile(d.document).scrollLocationIntoView('cur', { align: 'top' })
  await nextTick()
  // row content offset = 1000 + (500-100) = 1400; two rows of context = 2*(32+4)
  ok('the row is parked two rows below the top', d.scrolled, [{ top: 1400 - 72, behavior: 'smooth' }])
}

{
  // Where the row would land, given that scrollTop: context above = 2 rows.
  const d = dom({ rowTop: 500, zoneTop: 100, scrollTop: 1000, rowH: 32 })
  compile(d.document).scrollLocationIntoView('cur', { align: 'top' })
  await nextTick()
  const rowContentTop = 1000 + (500 - 100)
  const landedAt = 100 + (rowContentTop - d.scrolled[0].top)
  ok('…which leaves exactly two rows visible above it', landedAt - 100, 72)
}

{
  const d = dom({ rowTop: 120, zoneTop: 100, scrollTop: 0 })
  compile(d.document).scrollLocationIntoView('cur', { align: 'top' })
  await nextTick()
  ok('a row near the top clamps at 0 rather than scrolling negative', d.scrolled, [{ top: 0, behavior: 'smooth' }])
}

{
  // Row height is read off the row, so a restyle moves the context with it.
  const d = dom({ rowTop: 500, zoneTop: 100, scrollTop: 0, rowH: 40 })
  compile(d.document).scrollLocationIntoView('cur', { align: 'top' })
  await nextTick()
  ok('context follows the row height (40+4 → 88px)', d.scrolled, [{ top: 400 - 88, behavior: 'smooth' }])
}

// ── 3. the other callers keep centering ─────────────────────────────────
console.log('\nLocate — the watchers keep their centering\n')

{
  const d = dom()
  compile(d.document).scrollLocationIntoView('cur')
  await nextTick()
  ok('no alignment option still centers', [d.scrolled.length, d.intoView], [0, [{ block: 'center', behavior: 'smooth' }]])
}

{
  const d = dom({ hasZone: false })
  compile(d.document).scrollLocationIntoView('cur', { align: 'top' })
  await nextTick()
  ok('a row outside the browse zone falls back to centering', d.intoView, [{ block: 'center', behavior: 'smooth' }])
}

// ── 4. the check can actually fail ───────────────────────────────────────
// Rebuild the pre-fix function — no target expansion, and a plain centering
// scroll — and require it to reproduce both reported symptoms.
console.log('\ncheck sensitivity\n')
const oldLocate = locateBody
  .replace('    expanded[nodeId] = true\n', '')
  .replace("scrollLocationIntoView(nodeId, { align: 'top' })", 'scrollLocationIntoView(nodeId)')
ok('the pre-fix body is a strict rewrite of the shipped one', oldLocate !== locateBody, true)

const compileOld = (document) => new Function('deps', `
  const { expandedNodes, locationTree, findAncestorIds, nextTick, document } = deps
  function scrollLocationIntoView(locationId, { align = 'center' } = {}) { ${scrollBody} }
  function scrollToNode(nodeId) { ${oldLocate} }
  return { scrollToNode }
`)({ expandedNodes: TREE.expandedNodes, locationTree: TREE.locationTree, findAncestorIds: TREE.findAncestorIds, nextTick, document })

TREE.expandedNodes.value = {}
{
  const d = dom()
  compileOld(d.document).scrollToNode('cur')
  await nextTick()
  ok('pre-fix: the current location stayed collapsed (symptom 1)', TREE.expandedNodes.value.cur, undefined)
  ok('pre-fix: it centered instead of parking near the top (symptom 2)',
    [d.scrolled.length, d.intoView], [0, [{ block: 'center', behavior: 'smooth' }]])
}

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
