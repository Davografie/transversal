/**
 * Executable check for the tree's create rows under a filter.
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image, the same
 * way as the other checks:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-tree-create-rows.mjs
 *
 * The report: "I don't see how I can create an occupant at the moment. I've
 * filtered on USA, and I see the tree now without creation nodes." — and the
 * rule the author chose: "Occupants and zones on filtered location and its
 * sub-locations, or when the location is explicitly expanded."
 *
 * The inline add rows are the tree's **only** create entry point, and
 * `showAddRows` used to switch them off for the whole tree whenever any chip or
 * focus was active — so filtering removed entity creation entirely. The rule is
 * now per level: the plain view offers them everywhere; a place the filter
 * matched and its sub-locations offer them; and any level the GM expanded by hand
 * offers them.
 *
 * `useLocationTree` is the shipped module, imported and driven directly, so these
 * are the real rows rather than a restatement of the rule.
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
const { useLocationTree } = await import('../src/composables/useLocationTree.js')

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}

const U = (id, name, universe, children = []) => ({ id, name, kind: 'universe', universe, children })
const L = (id, name, universe, children = []) => ({ id, name, kind: 'location', universe, children })
const E = (id, name, type, currentLocation, currentUniverse) =>
  ({ id, name, type, currentLocation, currentUniverse })

// USA → Washington → White House, plus a sibling place and a place holding
// nobody — the last is the case a filter creates and an empty place has always
// had. The *last* child of a level has a child of its own, so expanding it is the
// case the trailing add row has to read correctly.
const TREE = [
  U('u-earth', 'Earth', 'earth', [
    L('loc-usa', 'USA', 'earth', [
      L('loc-washington', 'Washington', 'earth', [
        L('loc-white-house', 'White House', 'earth'),
      ]),
      L('loc-ny', 'New York', 'earth', [
        L('loc-albany', 'Albany', 'earth'),
      ]),
    ]),
    L('loc-canada', 'Canada', 'earth'),
    L('loc-empty', 'Empty Place', 'earth', [
      L('loc-attic', 'The Attic', 'earth'),
    ]),
  ]),
]

const ENTITIES = [
  E('u-earth', 'Earth', 'UNIVERSE', null, 'earth'),
  E('loc-usa', 'USA', 'LOCATION', 'u-earth', 'earth'),
  E('loc-washington', 'Washington', 'LOCATION', 'loc-usa', 'earth'),
  E('loc-white-house', 'White House', 'LOCATION', 'loc-washington', 'earth'),
  E('loc-ny', 'New York', 'LOCATION', 'loc-usa', 'earth'),
  E('loc-albany', 'Albany', 'LOCATION', 'loc-ny', 'earth'),
  E('loc-canada', 'Canada', 'LOCATION', 'u-earth', 'earth'),
  E('loc-empty', 'Empty Place', 'LOCATION', 'u-earth', 'earth'),
  E('loc-attic', 'The Attic', 'LOCATION', 'loc-empty', 'earth'),
  E('gmc-official', 'Official', 'GMC', 'loc-washington', 'earth'),
  E('gmc-mountie', 'Mountie', 'GMC', 'loc-canada', 'earth'),
]

// `useLocationTree` holds module-level singleton state, so every case gets a
// fresh tree array (a same-reference assignment would not invalidate the
// computeds) and a fresh expansion map.
function tree({ filtered = ENTITIES, chips = [], expanded = {} } = {}) {
  const t = useLocationTree({
    entities: ref(ENTITIES),
    filteredEntities: ref(filtered),
    activeFilters: ref(chips),
    currentUniverse: ref('earth'),
  })
  t.locationTree.value = JSON.parse(JSON.stringify(TREE))
  t.expandedNodes.value = { ...expanded }
  t.setFocus('')
  return t
}

const addRows = (t) => t.flatTree.value.filter((n) => n.kind === 'add')
const on = (t, parentId, addType) =>
  addRows(t).find((n) => n.parentId === parentId && n.addType === addType) || null
const at = (t, parentId) => addRows(t).filter((n) => n.parentId === parentId).map((n) => n.name)

const NAME_USA = [{ type: 'name', value: 'USA' }]
const TYPE_GMC = [{ type: 'entityType', value: 'GMC' }]
const NAME_EMPTY = [{ type: 'name', value: 'Empty Place' }]

// ── 1. the plain view is unchanged ──────────────────────────────────────
console.log('\nplain view — every open level still offers its rows\n')

{
  const t = tree()
  ok('the root closes the tree with "add universe"', on(t, '', 'universe')?.name, 'add universe')
  ok('the universe offers "add location"', on(t, 'u-earth', 'location')?.name, 'add location')
  ok('a location that is closed offers nothing', at(t, 'loc-usa'), [])

  const expanded = tree({ expanded: { 'loc-usa': true } })
  ok('expanding a location offers an occupant row and a zone row',
    at(expanded, 'loc-usa'), ['add occupant', 'add zone'])
  ok('the zone row names its parent', on(expanded, 'loc-usa', 'zone')?.parentId, 'loc-usa')
  ok('the occupant row names its parent', on(expanded, 'loc-usa', 'occupant')?.parentId, 'loc-usa')
}

// ── 1b. a level that ends on an expanded child ──────────────────────────
// The author: *"Show it only when the level doesn't end on an expanded child. …
// if the last child is expanded then it becomes ambiguous what I'm creating a
// zone for."*
console.log('\na level ending on an expanded child — the trailing row is withheld\n')

{
  const deep = tree({ expanded: { 'loc-usa': true, 'loc-ny': true } })
  ok('the parent withholds its zone row', at(deep, 'loc-usa'), ['add occupant'])
  ok('the child it ends on still offers its own', at(deep, 'loc-ny'), ['add occupant', 'add zone'])
  ok('the expanded child really did draw a child of its own',
    deep.flatTree.value.some((n) => n.id === 'loc-albany'), true)

  // The child has to be *collapsed* to get the row back — so the parent is not
  // left without a way to add a zone.
  const back = tree({ expanded: { 'loc-usa': true, 'loc-ny': false } })
  ok('collapsing that child brings the parent\'s row back',
    at(back, 'loc-usa'), ['add occupant', 'add zone'])

  // A filter draws its path open and a filter-opened level cannot be collapsed,
  // so the rule must not key on what is *on screen* — only on the GM's own
  // expand. Otherwise the filtered place would lose its row with no way back.
  const filteredDeep = tree({
    filtered: ENTITIES.filter((e) => ['loc-usa', 'loc-washington', 'loc-ny', 'loc-albany'].includes(e.id)),
    chips: NAME_USA,
  })
  ok('a filter-drawn child does not withhold the parent\'s row',
    at(filteredDeep, 'loc-usa'), ['add occupant', 'add zone'])

  // The same rule for a universe's "add location" row.
  const uni = tree({ expanded: { 'loc-empty': true } })
  ok('a universe ending on an expanded child withholds "add location"', at(uni, 'u-earth'), [])
  ok('collapsing it brings "add location" back',
    at(tree({ expanded: { 'loc-empty': false } }), 'u-earth'), ['add location'])
}

// ── 2. a filtered place and its sub-locations ───────────────────────────
console.log('\nfiltered on USA — the place and its sub-locations offer rows\n')

{
  const matched = ENTITIES.filter((e) =>
    ['loc-usa', 'loc-washington', 'loc-white-house', 'gmc-official'].includes(e.id))
  const t = tree({ filtered: matched, chips: NAME_USA })

  ok('the filtered place offers both rows', at(t, 'loc-usa'), ['add occupant', 'add zone'])
  ok('a sub-location offers them too', at(t, 'loc-washington'), ['add occupant', 'add zone'])
  ok('and a sub-location of that', at(t, 'loc-white-house'), ['add occupant', 'add zone'])
  ok('a place outside the filter is not drawn at all', at(t, 'loc-canada'), [])
  // The universe is not the filtered *place*, so it waits to be expanded.
  ok('the universe does not claim the rows', at(t, 'u-earth'), [])
  ok('nor does the root', addRows(t).some((n) => n.addType === 'universe'), false)
}

// ── 3. a chip that names no place ───────────────────────────────────────
console.log('\na type chip — rows follow the GM\'s expand, not the filter\n')

{
  const t = tree({ filtered: ENTITIES.filter((e) => e.type === 'GMC'), chips: TYPE_GMC })
  ok('no level claims the rows on its own', addRows(t).map((n) => n.parentId), [])
  ok('the paths to the matched occupants are still drawn',
    t.flatTree.value.filter((n) => n.kind === 'location').map((n) => n.id),
    ['loc-usa', 'loc-washington', 'loc-canada'])

  const opened = tree({
    filtered: ENTITIES.filter((e) => e.type === 'GMC'),
    chips: TYPE_GMC,
    expanded: { 'loc-usa': true },
  })
  ok('expanding a level by hand offers its rows', at(opened, 'loc-usa'), ['add occupant', 'add zone'])
}

// ── 4. the row survives an empty roster ─────────────────────────────────
console.log('\nan emptied roster — the row is offered anyway\n')

{
  const t = tree({ filtered: ENTITIES.filter((e) => e.id === 'loc-empty'), chips: NAME_EMPTY })
  ok('the matched place is drawn with no occupants', at(t, 'loc-empty'), ['add occupant', 'add zone'])
}

// ── 5. the rule this replaced, which must reproduce the report ──────────
console.log('\nthe pre-fix rule — no rows anywhere while a chip is active\n')

const preFixShowsRows = (chips) =>
  !chips.some((f) => ['entityType', 'name', 'unpublished', 'player'].includes(f.type))

ok('pre-fix: the USA chip switched the rows off tree-wide', preFixShowsRows(NAME_USA), false)
ok('pre-fix: so did the chip on the emptied place', preFixShowsRows(NAME_EMPTY), false)
ok('pre-fix: and the type chip', preFixShowsRows(TYPE_GMC), false)
ok('shipped: the filtered place has them', at(tree({ filtered: ENTITIES.filter((e) =>
  ['loc-usa', 'gmc-official'].includes(e.id)), chips: NAME_USA }), 'loc-usa'), ['add occupant', 'add zone'])

// ── 6. the create wiring a zone row needs ───────────────────────────────
console.log('\nthe create flow — a zone is parented by an edge\n')

const { readFileSync } = await import('node:fs')
const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8')
const CRUD = read('../src/composables/useEntityCrud.js')
const PANEL = read('../src/components/GmPanel.vue')

ok('creating a location under a parent posts the super edge',
  /formData\.type === 'LOCATION' && formData\.location/.test(CRUD) &&
  /edges\/\$\{formData\.location\}/.test(CRUD), true)
ok('an occupant or a zone inherits the row\'s parent as the default location',
  /addType === 'occupant' \|\| ctx\?\.addType === 'zone'/.test(PANEL), true)
ok('a zone row opens the create panel as a LOCATION', /zone: 'LOCATION'/.test(PANEL), true)
ok('the create listener refreshes the tree, not only the entity list',
  /await createEntity\(payload\); bus\.emit\('locations-changed'\)/.test(PANEL), true)

console.log(`\n${pass} passed, ${fail} failed\n`)
process.exit(fail ? 1 : 0)
