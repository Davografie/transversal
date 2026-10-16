/**
 * Executable check for inner locations: a location an **entity** carries.
 *
 * The human's design, 2026-10-16: *"don't render inner locations as nested under
 * characters, but put them in the entity edit panel. Then open them as child
 * panels."* Plus: create one from there, and no unlink yet.
 *
 * The model is backend-platform's ([[B308]]): one `super` edge from the location
 * to its carrier, exposed as `Entity.carriedLocations` and `Entity.carrier`. The
 * endpoint reports a carrier as a third kind — `node_type: 'carrier'` — whose
 * universe is its own and need not be the carried location's.
 *
 * Run it against the frontend image, the same way as the other checks:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-inner-locations.mjs
 *
 * The tree half is **behavioural**: `dropCarriers` is exported and driven here on
 * the shape the live endpoint actually returns (a carrier whose only child is the
 * carried location, flagged `carried: true`). The panel half is read from the
 * source, because a Vue component is not reachable from node — the browser half is
 * `e2e/tests/inner-locations.spec.js`.
 */
import { readFileSync } from 'node:fs'
import { register } from 'node:module'

// `useLocationTree` imports through the `@/` alias, which plain node cannot
// resolve, so map it to `src/` before pulling the module in.
register('data:text/javascript,' + encodeURIComponent(`
export async function resolve(specifier, context, next) {
  if (specifier.startsWith('@/')) {
    return next(new URL('./src/' + specifier.slice(2), 'file:///app/').href, context)
  }
  return next(specifier, context)
}
`))
const { dropCarriers } = await import('../src/composables/useLocationTree.js')

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}

const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8')
const PANEL = read('../src/components/gm/GmEntityEditPanel.vue')
const CRUD = read('../src/composables/useEntityCrud.js')

// ── 1. the tree drops carriers, and everything they hold ────────────────
console.log('\na carried location is not a place in the tree\n')

// The live shape, verbatim: a top-level carrier in its own universe whose only
// child is the carried location (universe `earth`), flagged `carried: true`.
const live = [
  { id: 'u1', name: 'Earth', node_type: 'universe', children: [{ id: 'loc-1', name: 'JFK Airport', node_type: 'location' }] },
  { id: 'u2', name: 'Three Realms', node_type: 'universe', children: [] },
  {
    id: 'character-20809', name: 'Phaos Tyish', node_type: 'carrier', universe: 'three_realms', carried: false,
    children: [{ id: 'loc-345978606', name: 'Phaos Tyish Qihai', node_type: 'location', universe: 'earth', carried: true, children: [] }],
  },
]

const kept = dropCarriers(live)
ok('the universes survive, in order', kept.map((n) => n.id), ['u1', 'u2'])
ok('the carrier is gone', kept.some((n) => n.id === 'character-20809'), false)
ok('and the place it carried went with it, rather than surfacing as a root',
  JSON.stringify(kept).includes('loc-345978606'), false)
ok('an ordinary location is untouched', kept[0].children, [{ id: 'loc-1', name: 'JFK Airport', node_type: 'location' }])

// A carrier need not be top-level, and a sibling must not be collateral.
const nested = dropCarriers([
  { id: 'u1', node_type: 'universe', children: [
    { id: 'loc-a', node_type: 'location', children: [
      { id: 'gmc-1', node_type: 'carrier', children: [{ id: 'loc-inner', node_type: 'location' }] },
      { id: 'loc-b', node_type: 'location' },
    ] },
  ] },
])
ok('a carrier nested anywhere is dropped', JSON.stringify(nested).includes('gmc-1'), false)
ok('and its carried location with it', JSON.stringify(nested).includes('loc-inner'), false)
ok('while its sibling stays', nested[0].children[0].children.map((n) => n.id), ['loc-b'])

// The function must not edit what it was handed — the store may re-filter.
const before = JSON.stringify(live)
dropCarriers(live)
ok('the input is not mutated', JSON.stringify(live), before)

ok('an empty or missing tree is not an error', [dropCarriers([]), dropCarriers(undefined)], [[], []])
ok('a bare location list passes through', dropCarriers([{ id: 'loc-1', node_type: 'location' }]).length, 1)

// `kind` is the other spelling the tree accepts, so it must be honoured too.
ok('a carrier marked with `kind` is dropped as well',
  dropCarriers([{ id: 'c', kind: 'carrier' }, { id: 'l', kind: 'location' }]).map((n) => n.id), ['l'])

// ── 2. the fetch path actually uses it ──────────────────────────────────
console.log('\nthe tree store filters at the source\n')

const TREE = read('../src/composables/useLocationTree.js')
ok('the fetched tree is filtered before it is stored',
  /locationTree\.value = dropCarriers\(await r\.json\(\)\)/.test(TREE), true)
// Nothing else should need to know about the third kind: after this filter the
// only kinds left are universe and location, which is what the `kind` mapping and
// the universe marking both assume.
ok('so the rest of the tree still only distinguishes two kinds',
  (TREE.match(/node_type === 'universe' \? 'universe' : 'location'/g) || []).length, 2)

// ── 3. the entity panel owns the surface ────────────────────────────────
console.log('\nthe entity panel lists them, opens them, and makes one\n')

ok('the panel has the section', /<h4>Inner locations<\/h4>/.test(PANEL), true)
ok('gated to the kinds that can hold one — not a location, not a universe',
  /const canCarry = computed\(\(\) => !!form\.value\.type && !\['LOCATION', 'UNIVERSE'\]\.includes\(form\.value\.type\)\)/.test(PANEL), true)
ok('and the gate is what the section renders on', /v-if="canCarry"/.test(PANEL), true)
ok('the rows are the carried locations the entity read returns',
  /const carriedLocations = computed\(\(\) => selected\.value\?\.carriedLocations \|\| \[\]\)/.test(PANEL), true)
ok('and the read asks for both halves of the edge',
  /carriedLocations \{ id name currentUniverse \}/.test(CRUD) && /carrier \{ id name type \}/.test(CRUD), true)
ok('a row opens the location as a child panel, in this same component',
  /function openInnerLocation\(loc\)[\s\S]{0,400}panel\.open\(\{[\s\S]{0,120}component: GmEntityEditPanel/.test(PANEL), true)
ok('carrying the id and the title of the place it opens', (() => {
  const body = PANEL.slice(PANEL.indexOf('function openInnerLocation'), PANEL.indexOf('async function createInnerLocation'))
  return /title: loc\.name/.test(body) && /id: loc\.id/.test(body)
})(), true)
ok('and the row is clickable', /v-for="loc in carriedLocations"[\s\S]{0,120}@click="openInnerLocation\(loc\)"/.test(PANEL), true)

// Create: a new location whose parent is **this entity** — an edge, because the
// parent here need not be a location at all.
ok('creating one makes a location',
  /async function createInnerLocation\(\)[\s\S]{0,700}type: 'LOCATION'/.test(PANEL), true)
ok('and parents it to this entity by edge, not by field',
  /createInnerLocation[\s\S]{0,1400}POST[\s\S]{0,200}type: 'super'/.test(PANEL), true)
ok('naming this entity as the parent in the URL',
  /locations\/\$\{newId\}\/edges\/\$\{props\.entityId\}/.test(PANEL), true)
ok('and re-reading the entity so the new row appears',
  /createInnerLocation[\s\S]{0,1600}await selectEntity\(\{ id: props\.entityId \}\)/.test(PANEL), true)
ok('the section offers the create affordance',
  /class="zones-add"[\s\S]{0,400}@click="createInnerLocation"/.test(PANEL), true)

// The other half of the edge: a held place has to say so, since nothing in the
// tree will explain why it is not there.
ok('a carried location\'s own panel names who holds it',
  /Held by \{\{ carrierName \}\}/.test(PANEL), true)
ok('which is read from the entity, not from the form',
  /const carrierName = computed\(\(\) => selected\.value\?\.carrier\?\.name \|\| ''\)/.test(PANEL), true)

// Neither direction is authored by a field, so the auto-save must not carry them.
ok('the form does not carry them, so the auto-save cannot write them',
  /carriedLocations:/.test(read('../src/composables/useEntityCrud.js').slice(
    read('../src/composables/useEntityCrud.js').indexOf('form.value = {'),
    read('../src/composables/useEntityCrud.js').indexOf('return alreadyEditing'))), false)

// ── 4. the trap this feature actually hit ───────────────────────────────
// Adding those two fields, I put `//` comments *inside* the GraphQL document.
// GraphQL has no such syntax, so the query was a syntax error — and the failure
// was silent and total: `selectEntity` got no data, never set the entity, and
// `openEntityEdit` returned early, so NO entity panel opened at all. Every node
// check was green; only the browser showed it. Pin the class, not the instance.
console.log('\nno GraphQL document carries a JavaScript comment\n')

{
  const docs = [...CRUD.matchAll(/`([^`]*(?:query|mutation)\s*\([^`]*)`/g)].map((m) => m[1])
  ok('the composable has GraphQL documents to check (so this is not vacuous)', docs.length > 0, true)
  const dirty = docs.filter((d) => d.includes('//'))
  ok('and none of them contains `//`', dirty.length, 0)
  if (dirty.length) console.log(`         offender: ${JSON.stringify(dirty[0].slice(0, 120))}`)
}

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
