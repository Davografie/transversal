/**
 * Executable check for the tree's expand chevron.
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-tree-expand.mjs
 *
 * A change here was started and never finished. The intent: **▾ means nothing is
 * left hidden at that level; ▸ means press for the rest.** A level the filter (or
 * the focus chain) only partly reveals therefore reads ▸, and pressing it is what
 * brings the other children in. Two things were missing:
 *
 *  1. **Pressing ▸ revealed nothing.** The children it recursed into were pruned
 *     by the filter one frame later (`if (filterMode && !onPath) continue`), so
 *     the chevron flipped to ▾ over an unchanged list.
 *  2. **Collapsing a chain level broke the chain.** `expandedNodes[id] = false`
 *     skipped the child render entirely while the glyph was still forced to ▾,
 *     leaving a node drawn as open with nothing under it.
 *
 * Also pinned: collapsing returns the level to its baseline (the filter's path,
 * the chain) — except where the baseline already *is* everything, where it must
 * hide the lot or the press would do nothing at all. And the toggle takes the
 * state to move to from the row, because a level can open by default while
 * `expandedNodes[id]` is still undefined.
 *
 * Every assertion is a state the pre-fix code could not reach.
 */
import { register } from 'node:module'
import { ref } from 'vue'

register('data:text/javascript,' + encodeURIComponent(`
export async function resolve(specifier, context, next) {
  if (specifier.startsWith('@/')) {
    return next(new URL('./src/' + specifier.slice(2), 'file:///app/').href, context)
  }
  return next(specifier, context)
}
`))
const { useEntityFilter } = await import('../src/composables/useEntityFilter.js')
const { useLocationTree } = await import('../src/composables/useLocationTree.js')

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}

const U = (id, name, universe, children = []) => ({ id, name, kind: 'universe', universe, children })
const L = (id, name, universe, children = []) => ({ id, name, kind: 'location', universe, children })
const E = (id, name, type, currentLocation, currentUniverse) => ({ id, name, type, currentLocation, currentUniverse })

// Europe has three children but only one is ever inhabited; swamp has an on-chain
// child (Iron Roots), an off-chain sibling and a leaf hut with a roster.
const TREE = [
  U('u-earth', 'Earth', 'earth', [
    L('loc-europe', 'Europe', 'earth', [
      L('loc-fr', 'France', 'earth'),
      L('loc-de', 'Germany', 'earth'),
      L('loc-es', 'Spain', 'earth'),
    ]),
  ]),
  U('u-three', 'Three Realms', 'three_realms', [
    L('loc-swamp', 'swamp', 'three_realms', [
      L('loc-iron', 'Iron Roots', 'three_realms', [
        L('loc-forge', 'Bulwark Forge', 'three_realms'),
        L('loc-pond', 'Stillness Pond', 'three_realms'),
      ]),
      L('loc-grove', 'Iron Grove', 'three_realms', [
        // A place whose only child is on the filter's path, with somebody of its
        // own the filter drops — the shape that read ▾ while hiding its roster.
        L('loc-camp', 'The Camp', 'three_realms', [
          L('loc-tent', 'The Tent', 'three_realms'),
        ]),
      ]),
      L('loc-hut', 'The Hut', 'three_realms'),
    ]),
  ]),
]

const ENTITIES = [
  E('u-earth', 'Earth', 'UNIVERSE', null, 'earth'),
  E('u-three', 'Three Realms', 'UNIVERSE', null, 'three_realms'),
  E('loc-europe', 'Europe', 'LOCATION', 'u-earth', 'earth'),
  E('loc-fr', 'France', 'LOCATION', 'loc-europe', 'earth'),
  E('loc-de', 'Germany', 'LOCATION', 'loc-europe', 'earth'),
  E('loc-es', 'Spain', 'LOCATION', 'loc-europe', 'earth'),
  E('loc-swamp', 'swamp', 'LOCATION', 'u-three', 'three_realms'),
  E('loc-iron', 'Iron Roots', 'LOCATION', 'loc-swamp', 'three_realms'),
  E('loc-forge', 'Bulwark Forge', 'LOCATION', 'loc-iron', 'three_realms'),
  E('loc-pond', 'Stillness Pond', 'LOCATION', 'loc-iron', 'three_realms'),
  E('loc-grove', 'Iron Grove', 'LOCATION', 'loc-swamp', 'three_realms'),
  E('loc-camp', 'The Camp', 'LOCATION', 'loc-grove', 'three_realms'),
  E('loc-tent', 'The Tent', 'LOCATION', 'loc-camp', 'three_realms'),
  E('loc-hut', 'The Hut', 'LOCATION', 'loc-swamp', 'three_realms'),
  E('gmc-alice', 'Alice', 'GMC', 'loc-fr', 'earth'),
  E('gmc-bob', 'Bob', 'GMC', 'loc-iron', 'three_realms'),
  E('gmc-cara', 'Cara', 'GMC', 'loc-hut', 'three_realms'),
  // Echo Two shares The Camp with Echo One but does not match a "Echo One" chip.
  E('gmc-e1', 'Echo One', 'GMC', 'loc-tent', 'three_realms'),
  E('gmc-e2', 'Echo Two', 'GMC', 'loc-camp', 'three_realms'),
  // One in each of Europe's children, for the "baseline is already everything" case.
  E('gmc-a1', 'Alpha One', 'GMC', 'loc-fr', 'earth'),
  E('gmc-a2', 'Alpha Two', 'GMC', 'loc-de', 'earth'),
  E('gmc-a3', 'Alpha Three', 'GMC', 'loc-es', 'earth'),
]

function world({ chips = [], focus = '', universe = 'three_realms' } = {}) {
  const f = useEntityFilter(ref(ENTITIES))
  f.activeFilters.value = chips
  const t = useLocationTree({
    // The full list matters: it is what tells the chevron that a filter is
    // hiding people at a level whose own roster came back empty.
    entities: ref(ENTITIES),
    filteredEntities: f.filteredEntities,
    activeFilters: f.activeFilters,
    currentUniverse: ref(universe),
  })
  t.locationTree.value = JSON.parse(JSON.stringify(TREE))   // fresh array: computeds need a new reference
  t.expandedNodes.value = {}
  t.setFocus(focus)
  return t
}

const row = (t, id) => t.flatTree.value.find((n) => n.id === id)
const glyph = (t, id) => { const n = row(t, id); return n ? (n.expanded ? '▾' : '▸') : '—' }
const under = (t, id) => {
  const flat = t.flatTree.value
  const r = flat.find((n) => n.id === id)
  if (!r) return []
  return flat.filter((n) => n.depth === r.depth + 1 && n.id !== 'more:' + id)
}
const kids = (t, id) => under(t, id).filter((n) => n.kind === 'location').map((n) => n.name)
const roster = (t, id) => under(t, id).filter((n) => n.kind === 'occupant').map((n) => n.name)
// Press the chevron the way the row does: it names the state to move to.
const press = (t, id) => { const n = row(t, id); t.toggleTreeNode(id, !n.expanded) }
const chip = (v) => [{ type: 'name', value: v, label: v }]

// ── 1. a partly-revealed level reveals the rest when pressed ─────────────
console.log('\nfilter — ▸ brings the rest in\n')

{
  const t = world({ chips: chip('Alice') })
  ok('a partly-revealed level reads ▸', glyph(t, 'loc-europe'), '▸')
  ok('…and shows only the matched child', kids(t, 'loc-europe'), ['France'])
  press(t, 'loc-europe')
  ok('pressing ▸ reveals the other children', kids(t, 'loc-europe'), ['France', 'Germany', 'Spain'])
  ok('…and the glyph becomes ▾', glyph(t, 'loc-europe'), '▾')
  press(t, 'loc-europe')
  ok('pressing ▾ returns to the filter path', kids(t, 'loc-europe'), ['France'])
  ok('…and the glyph returns to ▸', glyph(t, 'loc-europe'), '▸')
}

{
  const t = world({ chips: chip('Alice') })
  ok('the filter path above it is not disturbed', kids(t, 'u-earth'), ['Europe'])
  ok('the matched occupant is still listed', roster(t, 'loc-fr'), ['Alice'])
}

// ── 2. a leaf whose roster is shown reads ▾, and can be hidden ──────────
console.log('\nfilter — the roster counts as content\n')

{
  const t = world({ chips: chip('Cara') })
  ok('a leaf with a listed roster reads ▾', glyph(t, 'loc-hut'), '▾')
  ok('…and the roster is shown', roster(t, 'loc-hut'), ['Cara'])
  press(t, 'loc-hut')
  ok('pressing ▾ hides it (nothing is left, so it hides the lot)', [glyph(t, 'loc-hut'), roster(t, 'loc-hut')], ['▸', []])
  press(t, 'loc-hut')
  ok('pressing ▸ brings it back', [glyph(t, 'loc-hut'), roster(t, 'loc-hut')], ['▾', ['Cara']])
}

// ── 2b. a level hiding its own roster may not claim to be expanded ───────
console.log('\nfilter — a hidden roster makes the level read ▸\n')

{
  // The reported case: The Camp's only child is on the path (so nothing is
  // hidden among its children) but the filter drops the person standing in The
  // Camp itself. The filtered roster is empty, which used to satisfy the roster
  // check vacuously and draw ▾ over a hidden relative.
  const t = world({ chips: chip('Echo One') })
  ok('all children shown', kids(t, 'loc-camp'), ['The Tent'])
  ok('…but a hidden occupant still reads ▸', glyph(t, 'loc-camp'), '▸')
  ok('…and neither occupant is listed yet', roster(t, 'loc-camp'), [])
  ok('the matched one is listed where they are', roster(t, 'loc-tent'), ['Echo One'])
  press(t, 'loc-camp')
  ok('pressing ▸ reveals the whole roster, not just the matched part',
    roster(t, 'loc-camp'), ['Echo Two'])
  ok('…and then it reads ▾', glyph(t, 'loc-camp'), '▾')
  press(t, 'loc-camp')
  ok('pressing ▾ returns to the filtered view', [glyph(t, 'loc-camp'), roster(t, 'loc-camp')], ['▸', []])
}

// ── 3. when the baseline is already everything, ▾ has to hide ────────────
console.log('\nfilter — a fully-matched level still collapses\n')

{
  const t = world({ chips: chip('Alpha') })
  ok('every child matched → nothing hidden → ▾', glyph(t, 'loc-europe'), '▾')
  ok('…with all three on screen', kids(t, 'loc-europe'), ['France', 'Germany', 'Spain'])
  press(t, 'loc-europe')
  ok('pressing ▾ hides them rather than doing nothing',
    [glyph(t, 'loc-europe'), kids(t, 'loc-europe')], ['▸', []])
  press(t, 'loc-europe')
  ok('pressing ▸ shows them again', glyph(t, 'loc-europe'), '▾')
}

// ── 4. the focus chain: partial reveal, and a collapse that heals ────────
console.log('\nfocus — the chain collapses back to the chain\n')

{
  const t = world({ focus: 'loc-iron' })
  ok('a chain level with off-chain siblings reads ▸', glyph(t, 'loc-swamp'), '▸')
  ok('…and shows the on-chain child only', kids(t, 'loc-swamp'), ['Iron Roots'])
  ok('…with a "… N more" stub for the rest', !!t.flatTree.value.find((n) => n.id === 'more:loc-swamp'), true)
  press(t, 'loc-swamp')
  ok('pressing ▸ brings the siblings in', kids(t, 'loc-swamp'), ['Iron Roots', 'Iron Grove', 'The Hut'])
  ok('…and drops the stub', [glyph(t, 'loc-swamp'), !!t.flatTree.value.find((n) => n.id === 'more:loc-swamp')], ['▾', false])
  press(t, 'loc-swamp')
  ok('pressing ▾ collapses back to the chain, not to nothing',
    [glyph(t, 'loc-swamp'), kids(t, 'loc-swamp')], ['▸', ['Iron Roots']])
  ok('the chain itself is still on screen (the old bug lost it)', !!row(t, 'loc-iron'), true)
}

// ── 5. the plain view keeps traditional chevron behaviour ───────────────
console.log('\nplain — open by default, and collapsible\n')

{
  const t = world({})
  ok('the current universe is open by default', [glyph(t, 'u-three'), kids(t, 'u-three')], ['▾', ['swamp']])
  ok('another universe is closed', glyph(t, 'u-earth'), '▸')
  press(t, 'u-three')
  ok('pressing ▾ collapses it on the first press', [glyph(t, 'u-three'), kids(t, 'u-three')], ['▸', []])
  press(t, 'u-three')
  ok('pressing ▸ opens it again', [glyph(t, 'u-three'), kids(t, 'u-three')], ['▾', ['swamp']])
}

// ── 6. the toggle contract itself ───────────────────────────────────────
console.log('\ntoggle contract\n')

{
  const t = world({})
  t.toggleTreeNode('loc-europe', false)
  ok('it stores the state it is told to move to (false)', t.expandedNodes.value['loc-europe'], false)
  t.toggleTreeNode('loc-europe', true)
  ok('…and true', t.expandedNodes.value['loc-europe'], true)
  t.toggleTreeNode('loc-europe')
  ok('a caller that passes nothing still toggles', t.expandedNodes.value['loc-europe'], false)
  ok('a default-open row names false as its next state, so one press closes it',
    !row(t, 'u-three').expanded, false)
}

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
