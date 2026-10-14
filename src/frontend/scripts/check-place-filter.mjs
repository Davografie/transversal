/**
 * Executable check for the tree's filter chips — a **place** by name, and the
 * **unpublished** status.
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
const { NO_PLAYER_HOLDINGS } = await import('../src/constants/entityTypes.js')

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}

const U = (id, name, universe, children = []) => ({ id, name, kind: 'universe', universe, children })
const L = (id, name, universe, children = []) => ({ id, name, kind: 'location', universe, children })
const E = (id, name, type, currentLocation, currentUniverse, unpublished = false) =>
  ({ id, name, type, currentLocation, currentUniverse, unpublished })

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
  // An unpublished universe with nothing unpublished inside it: the status chip
  // still has to reach it.
  U('universe-emberline', 'The Emberline', 'emberline'),
]

const ENTITIES = [
  E('universe-earth', 'Earth', 'UNIVERSE', null, 'earth'),
  E('universe-three_realms', 'Three Realms', 'UNIVERSE', null, 'three_realms'),
  E('universe-emberline', 'The Emberline', 'UNIVERSE', null, 'emberline', true),        // a draft universe
  E('loc-uk', 'United Kingdom', 'LOCATION', 'universe-earth', 'earth'),
  E('loc-scotland', 'Scotland', 'LOCATION', 'loc-uk', 'earth'),
  E('location-craigmuir', 'Craigmuir', 'LOCATION', 'loc-scotland', 'earth'),
  E('location-stag', "The Stag's Head", 'LOCATION', 'loc-scotland', 'earth', true),   // a draft
  E('loc-unrelated', 'Somewhere Else', 'LOCATION', 'universe-earth', 'earth'),
  E('loc-iron-roots', 'Iron Roots', 'LOCATION', 'universe-three_realms', 'three_realms'),
  E('loc-yinling', 'Yinling Creek', 'LOCATION', 'universe-three_realms', 'three_realms'),
  E('gmc-moira', 'Moira McCoy', 'GMC', 'location-craigmuir', 'earth'),
  E('gmc-alastair', 'Alastair Rennie', 'GMC', 'location-craigmuir', 'earth'),
  E('gmc-tam', 'Tam Dodd', 'GMC', 'location-stag', 'earth', true),                     // a draft occupant
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

// ── 3. the status chip: "what needs attention" ──────────────────────────
console.log('\nstatus — filter by "unpublished"\n')

const CHIP_UNPUBLISHED = [{ type: 'unpublished', value: 'true', label: 'Unpublished' }]

{
  const f = filter(ENTITIES, [])
  f.filterInput.value = 'unp'
  ok('typing "unp" offers the status chip',
    f.suggestions.value.some((s) => s.filterType === 'unpublished'), true)
  f.filterInput.value = 'draft'
  ok('…and "draft" finds it too, since that is what the rows call it',
    f.suggestions.value.some((s) => s.filterType === 'unpublished'), true)
}

{
  const f = filter(ENTITIES, CHIP_UNPUBLISHED)
  ok('the chip keeps only drafts', ids(f.filteredEntities.value), ['gmc-tam', 'location-stag', 'universe-emberline'])
}

{
  const { flat } = scopedTree(ENTITIES, CHIP_UNPUBLISHED)
  const got = flatIds(flat)
  ok('a draft place is drawn', got.includes('location-stag'), true)
  ok('a draft occupant is drawn', got.includes('gmc-tam'), true)
  ok('…and a published place only as the path to them',
    ['loc-scotland', 'loc-uk', 'universe-earth'].every((id) => got.includes(id)), true)
  ok('a published place with no drafts under it is not drawn', got.includes('loc-iron-roots'), false)
  // The seed matters here: nothing unpublished is *inside* the Emberline, so only
  // a universe that matched can put it on the populated path.
  ok('a draft universe with no draft descendants draws itself', got.includes('universe-emberline'), true)
}

// ── suggestions: the canonical order, revealed a page at a time ─────────
// The human: *"Replace the hard cap with a lazy-load infinite scroll. It'd also be
// a good idea to sort the results deterministically, follow the sorting standard
// (entity type, then alphabetical)."* Measured live before this: "wang" matched 21
// rows, the box showed the first 10 **in database order**, and the last ten Wang
// GMCs could not be reached at all — no query surfaced them. Two guards: the order
// is rank → name → id, and the box reveals the whole match set a page at a time
// instead of truncating it.
console.log('\nsuggestions — the canonical order, a page at a time\n')

const AGENCY = new Map([
  ['q-char-main', { playerId: 'p1', main: true }],
  ['q-char-supp', { playerId: 'p2', main: false }],
])

// Every id carries the query letter, so one search matches the whole fixture and
// the assertion is about the *order*, not about what matches.
const MIXED = [
  E('q-loc-alpha', 'Alpha Place', 'LOCATION', null, 'earth'),
  E('q-gmc-zeta', 'Zeta', 'GMC', null, 'earth'),
  E('q-uni-earth', 'Earth', 'UNIVERSE', null, 'earth'),
  E('q-faction-beta', 'Beta Guild', 'FACTION', null, 'earth'),
  E('q-asset-ark', 'Ark', 'ASSET', null, 'earth'),
  E('q-gmc-alpha', 'Alpha', 'GMC', null, 'earth'),
  E('q-char-supp', 'Zed', 'CHARACTER', null, 'earth'),
  E('q-char-main', 'Beta', 'CHARACTER', null, 'earth'),
]

{
  const f = useEntityFilter(ref(MIXED), ref(NO_PLAYER_HOLDINGS), ref(AGENCY))
  f.filterInput.value = 'q'
  const got = f.suggestions.value.filter((s) => s.hint === 'name').map((s) => s.entityId)
  ok('entity rows follow rank → name → id', got, [
    'q-char-main', 'q-char-supp',                 // PC(MC), then PC(SC) — the agency decides
    'q-gmc-alpha', 'q-gmc-zeta',                  // then by type, alphabetical inside it
    'q-asset-ark', 'q-faction-beta', 'q-loc-alpha', 'q-uni-earth',
  ])
  ok('which is not the order the list arrived in (guard is real)',
    JSON.stringify(got) === JSON.stringify(MIXED.map((e) => e.id)), false)
}

{
  // The same type and the same name, differing only in case: the id is what makes
  // the order total rather than merely nearly-total.
  const twins = [
    E('q-gmc-b', 'wang', 'GMC', null, 'earth'),
    E('q-gmc-a', 'Wang', 'GMC', null, 'earth'),
  ]
  const f = useEntityFilter(ref(twins))
  f.filterInput.value = 'q'
  ok('equal names fall back to the id, so the order is total',
    f.suggestions.value.filter((s) => s.hint === 'name').map((s) => s.entityId),
    ['q-gmc-a', 'q-gmc-b'])
}

{
  const many = Array.from({ length: 25 }, (_, i) =>
    E(`q-gmc-${String(i).padStart(2, '0')}`, `Wang ${String(i).padStart(2, '0')}`, 'GMC', null, 'earth'))
  const f = useEntityFilter(ref(many))
  f.filterInput.value = 'wang'
  ok('the match set is not cut off at ten any more', f.suggestions.value.length, 20)
  ok('…and the box knows there is more of it', f.hasMore.value, true)
  f.loadMore()
  ok('the next page brings the rest', [f.suggestions.value.length, f.hasMore.value], [25, false])
}

// ── the suggestion that names one entity carries its id ─────────────────
// Picking a suggestion adds a chip; picking one that names a *single entity* also
// takes the GM to it (centre the tree, open the panel). That needs the id, and
// the id is not otherwise on the suggestion — it is only inside the synthetic
// `ent:<id>` key, which a consumer should not have to parse.
console.log('\nsuggestion → the entity it names\n')

const { readFileSync } = await import('node:fs')
const PANEL = readFileSync(new URL('../src/components/GmPanel.vue', import.meta.url), 'utf8')

{
  const f = useEntityFilter(ref(ENTITIES))
  f.filterInput.value = 'Craigmuir'
  const rows = f.suggestions.value
  const entity = rows.find((s) => s.hint === 'name')
  ok('an entity suggestion is offered', !!entity, true)
  ok('and it carries the entity id', entity?.entityId, 'location-craigmuir')
  ok('while a type chip carries none', rows.find((s) => s.hint === 'type')?.entityId, undefined)
  ok('and a universe chip carries none', rows.find((s) => s.hint === 'universe')?.entityId, undefined)
}

{
  // Both ways in have to go through the same handler, or Enter and the mouse
  // diverge — the exact class the filter's combobox work fixed once already.
  ok('the click uses the revealing handler',
    /@mousedown\.prevent="selectFilterSuggestion\(s\)"/.test(PANEL), true)
  ok('and so does Enter', /selectFilterSuggestion\(suggestions\.value\[i\]\)/.test(PANEL), true)
  ok('the chip is still added first', /function selectFilterSuggestion\(s\) \{\s*selectSuggestion\(s\)/.test(PANEL), true)
  ok('and only an entity suggestion goes further',
    /if \(s\.entityId\) revealEntity\(s\.entityId\)/.test(PANEL), true)
}

{
  const body = PANEL.slice(PANEL.indexOf('async function revealEntity'), PANEL.indexOf('async function revealEntity') + 1500)
  ok('it brings the tree\'s own surface forward', /mode\.value = 'prep'/.test(body) && /browseTab\.value = 'tree'/.test(body), true)
  ok('it opens the panel by the same path a row click takes', /onSelectEntity\(\{ id: entityId \}\)/.test(body), true)
  ok('it opens the level an occupant lives in, then centres on the entity itself',
    /expandToNode\(levelId\)/.test(body) && /centreOn\(entityId\)/.test(body), true)
  ok('a location is its own level', /entity\.type === 'LOCATION' \? entityId : \(entity\.currentLocation \|\| ''\)/.test(body), true)

  // The centring **waits for the layout to settle**, because one measured scroll is
  // not enough: the tree's rows keep shifting after the click, and a scroll computed
  // mid-flight lands on a position that no longer exists (measured live: the row
  // settled 624px below the fold while the scroll stopped at 52).
  const reveal = PANEL.slice(PANEL.indexOf('async function centreOn'), PANEL.indexOf('async function centreOn') + 1600)
  ok('the reveal waits for the row\'s position to hold still',
    /stable >= 2/.test(reveal) && /for \(let frame = 0; frame < 30; frame\+\+\)/.test(reveal), true)
  ok('it measures the row against its own scroller',
    /function rowOffset\(id\)[\s\S]{0,400}?row\.getBoundingClientRect\(\)\.top - zone\.getBoundingClientRect\(\)\.top/.test(PANEL), true)
  ok('then scrolls instantly — a smooth scroll would animate toward a stale position',
    /scrollLocationIntoView\(id, \{ align: 'top', behavior: 'auto' \}\)/.test(reveal), true)
  ok('and repeats: settle, scroll, settle, scroll',
    /for \(let attempt = 0; attempt < 3; attempt\+\+\) \{\s*await settle\(\)/.test(reveal), true)
  // The trap that made this flaky: stopping as soon as the row *looks* visible.
  // An interim layout can put it on screen and shift it back out (chromium
  // measured `scrollTop: 48` with the row 600px below the fold).
  ok('it never stops on "looks visible" — that interim layout does not last',
    /rowInView/.test(PANEL), false)
  ok('the wait is a timer, not rAF — rAF stops when a tab is not painted',
    /setTimeout\(resolve, 16\)/.test(reveal), true)
  ok('and it is bounded, so a row that never appears cannot spin',
    /frame < 30/.test(reveal), true)

  // Pre-fix: adding the chip touched neither the tree nor a panel.
  const preFix = 'selectSuggestion(s)'
  ok('pre-fix: adding the chip touched neither the tree nor a panel',
    [/scrollToNode/.test(preFix), /onSelectEntity/.test(preFix), /mode\.value/.test(preFix)], [false, false, false])
}

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
