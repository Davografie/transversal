/**
 * Executable check for the GM panel's player filter (B188).
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-player-filter.mjs
 *
 * The ask: "Be able to filter by player and see that player's characters."
 *
 * The subtle half is *which* player→entity index the filter may use. The tree
 * already had `buildAgencyIndex`, which answers "which ONE player holds this"
 * for the PC(MC)/PC(SC) buckets — and collapsing to a single holder is exactly
 * wrong for a filter: one human's per-device identities each hold their
 * characters (live, `character-20809` is held by eight player records), so a
 * filter for any record but the bucket's winner would find nothing. The filter
 * therefore reads `buildPlayerHoldings`, a multi-holder index over the same
 * payload, and the case below pins that difference rather than assuming it.
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
const { buildAgencyIndex, buildPlayerHoldings, NO_PLAYER_HOLDINGS } = await import('../src/constants/entityTypes.js')
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
    L('loc-hall', 'The Hall', 'earth', [L('loc-nook', 'The Nook', 'earth')]),
  ]),
]

const ENTITIES = [
  E('u-earth', 'Earth', 'UNIVERSE', null),
  E('loc-hall', 'The Hall', 'LOCATION', 'u-earth'),
  E('loc-nook', 'The Nook', 'LOCATION', 'loc-hall'),
  E('ch-main', 'Ola Main', 'CHARACTER', 'loc-hall'),
  E('ch-support', 'Ola Support', 'CHARACTER', 'loc-hall'),
  E('ch-shared', 'Shared Body', 'CHARACTER', 'loc-nook'),
  E('ch-other', 'Pip Body', 'CHARACTER', 'loc-hall'),
  E('ch-free', 'Nobody Body', 'CHARACTER', 'loc-hall'),
  E('gmc-1', 'A GMC', 'GMC', 'loc-hall'),
]

// Ola holds a main and a support. `ch-shared` is held by two records — the
// per-device shape — where PTDave's id sorts lower and so wins the bucket rule.
// player-4 holds nothing.
const PLAYERS = [
  { id: 'player-1', name: 'Ola', agency: [{ entityId: 'ch-main', main: true }, { entityId: 'ch-support', main: false }] },
  { id: 'player-2', name: 'PTDave', agency: [{ entityId: 'ch-shared', main: true }] },
  { id: 'player-9', name: 'DonDaefTablet', agency: [{ entityId: 'ch-shared', main: true }] },
  { id: 'player-3', name: 'Pip', agency: [{ entityId: 'ch-other', main: true }] },
  { id: 'player-4', name: 'Idle', agency: [] },
]

function world({ list = ENTITIES, holdings = buildPlayerHoldings(PLAYERS), expand = [] } = {}) {
  const f = useEntityFilter(ref(list), ref(holdings))
  const t = useLocationTree({
    entities: ref(list),
    filteredEntities: f.filteredEntities,
    agencyByEntity: ref(buildAgencyIndex(PLAYERS)),
    activeFilters: f.activeFilters,
    currentUniverse: ref('earth'),
  })
  t.locationTree.value = JSON.parse(JSON.stringify(TREE))
  t.expandedNodes.value = Object.fromEntries(expand.map((id) => [id, true]))
  t.setFocus('')
  return { f, t }
}

/** Offer the chips for `query` and take the one with `filterValue`. */
function take(f, query, filterValue) {
  f.filterInput.value = query
  const chip = f.suggestions.value.find((s) => s.filterType === 'player' && s.filterValue === filterValue)
  if (!chip) return null
  f.selectSuggestion(chip)
  return chip
}

const occupantIds = (t) => t.flatTree.value.filter((n) => n.kind === 'occupant').map((n) => n.id)
const filteredIds = (f) => f.filteredEntities.value.map((e) => e.id)

// ── 1. the index ─────────────────────────────────────────────────────────
console.log('\nthe player index — multi-holder, unlike the bucket rule\n')

{
  const h = buildPlayerHoldings(PLAYERS)
  ok('a player with agency is offered', [...h.byPlayer.keys()], ['player-1', 'player-2', 'player-9', 'player-3'])
  ok('a player holding nothing is not', h.byPlayer.has('player-4'), false)
  ok('the name is carried for the chip', h.byPlayer.get('player-1').name, 'Ola')
  ok('a solely-held entity has one holder', [...h.holders.get('ch-main')], ['player-1'])
  ok('a shared entity keeps BOTH holders', [...h.holders.get('ch-shared')].sort(), ['player-2', 'player-9'])
  ok('an entity nobody holds has no entry', h.holders.has('ch-free'), false)

  // The difference that makes this index necessary, asserted rather than
  // assumed: the bucket rule keeps one holder, and it is not player-9.
  ok('the bucket rule collapses the same entity to one holder',
    buildAgencyIndex(PLAYERS).get('ch-shared').playerId, 'player-2')
  ok('so the two indexes genuinely disagree about who holds it',
    buildAgencyIndex(PLAYERS).get('ch-shared').playerId !== 'player-9', true)
}

// ── 2. the chip is offered ───────────────────────────────────────────────
console.log('\ntyping a player name\n')

{
  const { f } = world()
  f.filterInput.value = 'Ola'
  const players = f.suggestions.value.filter((s) => s.filterType === 'player')
  ok('typing a name offers that player', players.map((s) => s.name), ['Ola'])
  ok('as a `player` chip, not a name chip', players[0].filterType, 'player')
  ok('labelled with the name, valuable by id', [players[0].filterLabel, players[0].filterValue], ['Ola', 'player-1'])
  ok('the hint says what kind of chip it is', players[0].hint, 'player')

  ok('a name with no holding player offers no player chip',
    (f.filterInput.value = 'Nobody', f.suggestions.value.filter((s) => s.filterType === 'player').length), 0)
}

// ── 3. taking it filters to that player's characters ─────────────────────
console.log('\nwhat the chip leaves on screen\n')

{
  const { f, t } = world()
  const chip = take(f, 'Ola', 'player-1')
  ok('the chip was available', !!chip, true)
  ok('the active filter is a player chip', f.activeFilters.value, [{ type: 'player', value: 'player-1', label: 'Ola' }])
  ok('only that player\'s characters match', filteredIds(f).sort(), ['ch-main', 'ch-support'])
  ok('and the tree draws exactly them', occupantIds(t).sort(), ['ch-main', 'ch-support'])
  // Path pruning, not "show everything": Pip's body is in the same location.
  ok('another player\'s character in the same place is not drawn',
    occupantIds(t).includes('ch-other'), false)
}

{
  // The per-device case. Via the bucket rule this filter would come back empty.
  const { f, t } = world()
  const chip = take(f, 'DonDaefTablet', 'player-9')
  ok('the second record\'s chip is offered', !!chip, true)
  ok('and finds the shared character the bucket rule would hide', occupantIds(t).sort(), ['ch-shared'])
}

{
  // A player chip must not stop being a *path* chip: the matched character's
  // ancestors still draw, so the tree can be read.
  const { f, t } = world()
  take(f, 'DonDaefTablet', 'player-9')
  const ids = t.flatTree.value.map((n) => n.id)
  ok('the ancestor path still draws', ['u-earth', 'loc-hall', 'loc-nook'].every((id) => ids.includes(id)), true)
}

// ── 4. chips stay additive ───────────────────────────────────────────────
console.log('\na player chip alongside the others\n')

{
  const { f, t } = world()
  take(f, 'Ola', 'player-1')
  f.filterInput.value = 'Pip Body'
  const nameChip = f.suggestions.value.find((s) => s.filterType === 'name' && s.name === 'Pip Body')
  ok('a name chip is still offered while a player chip is active', !!nameChip, true)
  if (nameChip) f.selectSuggestion(nameChip)
  ok('the two chips combine as a union, not a narrowing',
    filteredIds(f).sort(), ['ch-main', 'ch-other', 'ch-support'])
  ok('so both characters are drawn', occupantIds(t).sort(), ['ch-main', 'ch-other', 'ch-support'])
}

// ── 5. the chevron still means "press for the rest" ──────────────────────
console.log('\nan explicitly expanded level under a player chip\n')

{
  // The filter does not remove the roster from the tree — it hides it behind the
  // chevron, which is what the three glyphs promise. Pinned here because the
  // first draft of this check pre-expanded the level and read the full roster as
  // a failure: it is the documented contract, not a leak.
  const { f, t } = world({ expand: ['u-earth', 'loc-hall'] })
  take(f, 'Ola', 'player-1')
  ok('an open level shows the whole roster, matched or not',
    occupantIds(t).sort(), ['ch-free', 'ch-main', 'ch-other', 'ch-support', 'gmc-1'])
  ok('while the filter itself still matched only the two',
    filteredIds(f).sort(), ['ch-main', 'ch-support'])
}

// ── 6. absent index changes nothing ──────────────────────────────────────
console.log('\nno players supplied (the pre-existing call shape)\n')

{
  // The other suites call `useEntityFilter(entities)` with one argument; that
  // must keep working and simply offer no players.
  const f = useEntityFilter(ref(ENTITIES))
  f.filterInput.value = 'Ola'
  ok('no player chip is offered without the index',
    f.suggestions.value.filter((s) => s.filterType === 'player').length, 0)
  ok('and the old shape still filters by name',
    (f.selectSuggestion({ filterType: 'name', filterValue: 'ch-other', filterLabel: 'Pip Body' }), filteredIds(f)), ['ch-other'])
  ok('the empty holdings shape is what the default is',
    [...NO_PLAYER_HOLDINGS.byPlayer.keys()], [])
}

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
