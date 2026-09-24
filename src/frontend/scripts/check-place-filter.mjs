/**
 * Executable check for "filter the tree by a place".
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-place-filter.mjs
 *
 * `useEntityFilter` imports through the `@/` alias, which plain node cannot
 * resolve, so a tiny resolver hook maps `@/` → `src/` (the modules themselves
 * are the shipped ones either way).
 *
 * The report behind this: a GM at Iron Roots (Three Realms) filtered the tree on
 * **Scotland** (an Earth location) and got nothing but "… 17 more universes",
 * which expanded to "No entities found" — while four GMCs actually live inside
 * Scotland. Three separate faults, three guards here:
 *
 *  1. the name-chip scope matched the location id **exactly**, so occupants of
 *     its child locations were invisible ("at" worked, "in" did not);
 *  2. `populatedLocations` was seeded from **occupants only**, so a matched
 *     place that held nobody directly contributed no drawable node at all;
 *  3. **focus-mode stubbing stayed on under a filter** — it hid filter matches
 *     behind "… N more" and, at the root, printed a count taken from the focus
 *     chain ("… 17 more universes" = 18 roots minus the one on-screen universe).
 *
 * Every assertion below is a state the pre-fix code could not reach, so a
 * regression fails loudly rather than passing vacuously.
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

// Shaped like the real data: a location's `currentLocation` is its parent, and
// the occupants sit one and two levels under Scotland.
const TREE = [
  U('universe-earth', 'Earth', 'earth', [
    L('loc-uk', 'United Kingdom', 'earth', [
      L('loc-scotland', 'Scotland', 'earth', [
        L('location-craigmuir', 'Craigmuir', 'earth'),
        L('location-stag', "The Stag's Head", 'earth'),
      ]),
    ]),
  ]),
  U('universe-three_realms', 'Three Realms', 'three_realms', [
    L('loc-iron-roots', 'Iron Roots', 'three_realms'),
    L('loc-yinling', 'Yinling Creek', 'three_realms'),
  ]),
]

const ENTITIES = [
  E('universe-earth', 'Earth', 'UNIVERSE', null, 'earth'),
  E('universe-three_realms', 'Three Realms', 'UNIVERSE', null, 'three_realms'),
  E('loc-uk', 'United Kingdom', 'LOCATION', 'universe-earth', 'earth'),
  E('loc-scotland', 'Scotland', 'LOCATION', 'loc-uk', 'earth'),
  E('location-craigmuir', 'Craigmuir', 'LOCATION', 'loc-scotland', 'earth'),
  E('location-stag', "The Stag's Head", 'LOCATION', 'loc-scotland', 'earth'),
  E('loc-unrelated', 'Somewhere Else', 'LOCATION', 'universe-earth', 'earth'),
  E('loc-iron-roots', 'Iron Roots', 'LOCATION', 'universe-three_realms', 'three_realms'),
  E('loc-yinling', 'Yinling Creek', 'LOCATION', 'universe-three_realms', 'three_realms'),
  E('gmc-moira', 'Moira McCoy', 'GMC', 'location-craigmuir', 'earth'),
  E('gmc-alastair', 'Alastair Rennie', 'GMC', 'location-craigmuir', 'earth'),
  E('gmc-tam', 'Tam Dodd', 'GMC', 'location-stag', 'earth'),
  E('gmc-direct', 'Someone In Scotland', 'GMC', 'loc-scotland', 'earth'),
  E('gmc-elsewhere', 'Someone Else', 'GMC', 'loc-unrelated', 'earth'),
  E('char-ir', 'Rhys Iron Roots', 'CHARACTER', 'loc-iron-roots', 'three_realms'),
  E('gmc-yinling', 'Luo Ting', 'GMC', 'loc-yinling', 'three_realms'),
]

const ids = (arr) => arr.map((e) => e.id).sort()
const flatIds = (flat) => flat.map((n) => n.id)
const stubs = (flat) => flat.filter((n) => n.kind === 'more').map((n) => n.name)

// ── 1. the place scope reaches what is nested inside it ──────────────────
console.log('\nplace scope — "at/in it", not just "at it"\n')

const filter = (entities, filters) => {
  const f = useEntityFilter(ref(entities))
  f.activeFilters.value = filters
  return f
}
const CHIP_SCOTLAND = [{ type: 'name', value: 'Scotland', label: 'Scotland' }]

{
  const f = filter(ENTITIES, CHIP_SCOTLAND)
  const got = ids(f.filteredEntities.value)
  ok('the place itself matches', got.includes('loc-scotland'), true)
  ok('its child places match', [got.includes('location-craigmuir'), got.includes('location-stag')], [true, true])
  ok('an occupant two levels down matches (was excluded)', got.includes('gmc-moira'), true)
  ok('an occupant one level down matches (was excluded)', got.includes('gmc-tam'), true)
  ok('an occupant directly in the place still matches', got.includes('gmc-direct'), true)
  ok('an occupant outside the subtree does not', got.includes('gmc-elsewhere'), false)
  ok('another universe is not dragged in', [got.includes('char-ir'), got.includes('gmc-yinling')], [false, false])
}

{
  // The old rule, spelled out: name/id only, plus an exact location match.
  const oldRule = ENTITIES.filter((e) =>
    e.name.toLowerCase().includes('scotland') || e.id.toLowerCase().includes('scotland') ||
    e.currentLocation === 'loc-scotland')
  ok('the pre-fix rule excluded the nested occupants (guard is real)',
    [oldRule.some((e) => e.id === 'gmc-moira'), oldRule.some((e) => e.id === 'gmc-tam')], [false, false])
}

{
  const f = filter(ENTITIES, [{ type: 'name', value: 'Luo Ting', label: 'Luo Ting' }])
  ok('a chip naming a person matches only that person',
    ids(f.filteredEntities.value), ['gmc-yinling'])
}

{
  const f = filter(ENTITIES, [{ type: 'name', value: 'Earth', label: 'Earth' }])
  ok('a chip naming a universe still scopes by universe',
    ids(f.filteredEntities.value).includes('gmc-elsewhere'), true)
}

// ── 2. the tree draws the place and its occupants, with no bogus stub ─────
console.log('\ntree — the filter decides what is on screen\n')

/**
 * `useLocationTree` holds module-level singleton state, so each case gets a
 * fresh tree array (a same-reference assignment would not invalidate Vue's
 * computeds) and a reset expansion map.
 */
function scopedTree(entities, filters, { focus = 'loc-iron-roots', universe = 'three_realms', all = ENTITIES } = {}) {
  const f = typeof entities === 'object' && entities.filteredEntities ? entities : filter(entities, filters)
  const t = useLocationTree({
    // The unfiltered list too — production passes it, and it is what tells a
    // level whether the filter is hiding people of its own.
    entities: ref(all),
    filteredEntities: f.filteredEntities,
    activeFilters: f.activeFilters,
    currentUniverse: ref(universe),
  })
  t.locationTree.value = JSON.parse(JSON.stringify(TREE))
  t.expandedNodes.value = {}
  t.setFocus(focus)
  return { f, t, flat: t.flatTree.value }
}

{
  // The reported case: free-roam focus at Iron Roots, chip "Scotland".
  const { flat } = scopedTree(ENTITIES, CHIP_SCOTLAND)
  const got = flatIds(flat)
  ok('no "… N more universes" stub over the list', stubs(flat), [])
  ok('the Earth path to the place is drawn',
    ['universe-earth', 'loc-uk', 'loc-scotland'].every((id) => got.includes(id)), true)
  ok('the nested child places are drawn',
    ['location-craigmuir', 'location-stag'].every((id) => got.includes(id)), true)
  ok('the nested occupants are drawn',
    ['gmc-moira', 'gmc-alastair', 'gmc-tam', 'gmc-direct'].every((id) => got.includes(id)), true)
  ok('the focused Iron Roots branch is not shown (nothing matched there)',
    got.includes('loc-iron-roots'), false)
}

{
  // A match off the focus chain, inside the focused universe. Focus-mode
  // stubbing used to hide this branch behind a "… 1 more" stub.
  const { flat } = scopedTree(ENTITIES, [{ type: 'name', value: 'Luo Ting', label: 'Luo Ting' }])
  const got = flatIds(flat)
  ok('an off-chain match in the focused universe is drawn',
    [got.includes('loc-yinling'), got.includes('gmc-yinling')], [true, true])
  ok('…and is not hidden behind a stub', stubs(flat), [])
  ok('the focus branch itself is not forced in', got.includes('loc-iron-roots'), false)
}

{
  // A matched place with nobody anywhere inside it: it must still draw itself
  // (and its ancestors) rather than collapsing to an empty tree.
  const placesOnly = ENTITIES.filter((e) => e.type === 'LOCATION' || e.type === 'UNIVERSE')
  const { flat } = scopedTree(placesOnly, [{ type: 'name', value: 'Craigmuir', label: 'Craigmuir' }], { all: placesOnly })
  const got = flatIds(flat)
  ok('a matched place with no occupants still draws itself', got.includes('location-craigmuir'), true)
  ok('…along with its ancestor path',
    ['loc-scotland', 'loc-uk', 'universe-earth'].every((id) => got.includes(id)), true)
  ok('…and still no stub', stubs(flat), [])
}

{
  // A universe chip is a filter too: it must not be hidden behind the focus
  // root stub either.
  const { flat } = scopedTree(ENTITIES, [{ type: 'universe', value: 'earth', label: 'Earth' }])
  ok('a universe chip shows its universe, with no root stub',
    [flatIds(flat), stubs(flat)], [['universe-earth'], []])
}

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
