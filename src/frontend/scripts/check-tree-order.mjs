/**
 * Executable check for the location tree's occupant order.
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-tree-order.mjs
 *
 * The tree now reads the way the sheet's relationship list does — PC(MC),
 * PC(SC), PC, GMC, Asset, Faction, then alphabetical — because the two are the
 * same kind of list: entities of several types under one heading.
 *
 * What was wrong: `_sortOccupants` grouped on a three-value type priority and
 * stopped there. Ties kept the order the entity list arrived in, and that list is
 * **unsorted** — `list_all_entities` has no `SORT` clause — so the rows within a
 * group could move between loads. It also could not tell a main from a support
 * (`relatedEntities`-style payloads carry no agency) and had no name tiebreak.
 *
 * The required order is written out here rather than imported from the app's
 * `ENTITY_TYPE_ORDER`, so this fails if the order changes instead of agreeing
 * with it — the same choice the sheet's ordering test made.
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
const { buildAgencyIndex } = await import('../src/constants/entityTypes.js')
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
const E = (id, name, type, currentLocation, currentUniverse = 'earth') =>
  ({ id, name, type, currentLocation, currentUniverse })

const TREE = [
  U('u-earth', 'Earth', 'earth', [
    L('loc-hall', 'The Hall', 'earth', [
      L('loc-nook', 'The Nook', 'earth'),
    ]),
  ]),
]

// Deliberately supplied in a scrambled order: the whole point is that the tree
// does not depend on it.
const ENTITIES = [
  E('u-earth', 'Earth', 'UNIVERSE', null),
  E('loc-hall', 'The Hall', 'LOCATION', 'u-earth'),
  E('loc-nook', 'The Nook', 'LOCATION', 'loc-hall'),
  E('gmc-yannick', 'Yannick', 'GMC', 'loc-hall'),
  E('ch-zara', 'Zara', 'CHARACTER', 'loc-hall'),
  E('as-zeppelin', 'Zeppelin', 'ASSET', 'loc-hall'),
  E('ch-bea', 'Bea', 'CHARACTER', 'loc-hall'),
  E('gmc-dmitri', 'Dmitri', 'GMC', 'loc-hall'),
  E('ch-amos', 'Amos', 'CHARACTER', 'loc-hall'),
  E('as-ark', 'Ark', 'ASSET', 'loc-hall'),
  E('ch-cleo', 'Cleo', 'CHARACTER', 'loc-hall'),
  // In the child location, to show the order applies at every level.
  E('gmc-nina', 'Nina', 'GMC', 'loc-nook'),
  E('ch-ada', 'Ada', 'CHARACTER', 'loc-nook'),
]

// Zara and Amos are mains; Bea is a support; Cleo is played by nobody.
const PLAYERS = [
  { id: 'player-1', agency: [{ entityId: 'ch-zara', main: true }, { entityId: 'ch-bea', main: false }] },
  { id: 'player-2', agency: [{ entityId: 'ch-amos', main: true }] },
]

function world({ list = ENTITIES, agency = buildAgencyIndex(PLAYERS), expand = ['u-earth', 'loc-hall'] } = {}) {
  const f = useEntityFilter(ref(list))
  const t = useLocationTree({
    entities: ref(list),
    filteredEntities: f.filteredEntities,
    agencyByEntity: ref(agency),
    activeFilters: f.activeFilters,
    currentUniverse: ref('earth'),
  })
  t.locationTree.value = JSON.parse(JSON.stringify(TREE))
  t.expandedNodes.value = Object.fromEntries(expand.map((id) => [id, true]))
  t.setFocus('')
  return t
}

/** The occupant rows sitting directly under `id`, in render order. */
function occupantsOf(t, id) {
  const flat = t.flatTree.value
  const i = flat.findIndex((n) => n.id === id)
  if (i < 0) return []
  const out = []
  for (let k = i + 1; k < flat.length; k++) {
    if (flat[k].depth <= flat[i].depth) break
    if (flat[k].kind === 'occupant') out.push(flat[k].name)
  }
  return out
}

// ── 1. the order, written out ────────────────────────────────────────────
console.log('\noccupant order — the sheet\'s order, in the tree\n')

const EXPECTED = [
  'Amos', 'Zara',           // PC(MC), alphabetical
  'Bea',                    // PC(SC)
  'Cleo',                   // PC — played by nobody
  'Dmitri', 'Yannick',      // GMC, alphabetical
  'Ark', 'Zeppelin',        // Asset, alphabetical
]

{
  const t = world()
  ok('mains, then supports, then plain PCs, GMCs and assets', occupantsOf(t, 'loc-hall'), EXPECTED)
}

{
  const t = world({ expand: ['u-earth', 'loc-hall', 'loc-nook'] })
  ok('the same order holds one level down', occupantsOf(t, 'loc-nook'), ['Ada', 'Nina'])
}

// ── 2. it does not depend on the input order ─────────────────────────────
console.log('\ndeterminism\n')

{
  const forward = occupantsOf(world(), 'loc-hall')
  const reversed = occupantsOf(world({ list: [...ENTITIES].reverse() }), 'loc-hall')
  const shuffled = occupantsOf(world({ list: [...ENTITIES].sort(() => 0.5 - Math.random()) }), 'loc-hall')
  ok('reversing the entity list does not change it', reversed, EXPECTED)
  ok('shuffling it does not either', shuffled, EXPECTED)
  ok('all three agree', [forward.length === reversed.length && forward.length === shuffled.length], [true])
}

{
  // Names that compare equal under `sensitivity: 'base'` — the tie has to break
  // on something stable, or the pair could swap between loads.
  const twins = [
    E('u-earth', 'Earth', 'UNIVERSE', null),
    E('loc-hall', 'The Hall', 'LOCATION', 'u-earth'),
    E('gmc-b', 'Robin', 'GMC', 'loc-hall'),
    E('gmc-a', 'robin', 'GMC', 'loc-hall'),
  ]
  const t = world({ list: twins, agency: new Map(), expand: ['u-earth', 'loc-hall'] })
  ok('a case-only tie breaks on id, not on arrival order', occupantsOf(t, 'loc-hall'), ['robin', 'Robin'])
}

{
  // Alphabetical is case-insensitive: lowercase must not sort after uppercase.
  const mixed = [
    E('u-earth', 'Earth', 'UNIVERSE', null),
    E('loc-hall', 'The Hall', 'LOCATION', 'u-earth'),
    E('gmc-z', 'bea', 'GMC', 'loc-hall'),
    E('gmc-y', 'Ada', 'GMC', 'loc-hall'),
  ]
  const t = world({ list: mixed, agency: new Map(), expand: ['u-earth', 'loc-hall'] })
  ok('alphabetical ignores case', occupantsOf(t, 'loc-hall'), ['Ada', 'bea'])
}

// ── 3. the agency index behind PC(MC) / PC(SC) ───────────────────────────
console.log('\nagency index — one holder per entity\n')

{
  const idx = buildAgencyIndex(PLAYERS)
  ok('a main is an MC', idx.get('ch-zara'), { playerId: 'player-1', main: true })
  ok('a non-main edge is an SC', idx.get('ch-bea'), { playerId: 'player-1', main: false })
  ok('an unheld entity has no entry', idx.has('ch-cleo'), false)
}

{
  // One entity, several player records (one human's per-device identities). The
  // backend's `get_agency_for_entity` sorts `main` first then player id, and the
  // client must not disagree with it.
  const multi = [
    { id: 'player-9', agency: [{ entityId: 'ch-x', main: false }] },
    { id: 'player-3', agency: [{ entityId: 'ch-x', main: false }] },
    { id: 'player-7', agency: [{ entityId: 'ch-x', main: true }] },
  ]
  ok('a main claim wins over an earlier non-main edge',
    buildAgencyIndex(multi).get('ch-x'), { playerId: 'player-7', main: true })
  const ties = [
    { id: 'player-9', agency: [{ entityId: 'ch-y', main: true }] },
    { id: 'player-3', agency: [{ entityId: 'ch-y', main: true }] },
  ]
  ok('among equals the lowest player id wins',
    buildAgencyIndex(ties).get('ch-y'), { playerId: 'player-3', main: true })
  ok('an empty payload is an empty index', buildAgencyIndex(undefined).size, 0)
}

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
