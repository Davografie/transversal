/**
 * Executable check for the trait-tree helpers (container traits).
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend:/work:ro \
 *     -w /work transversal2-frontend:latest node scripts/check-trait-tree.mjs
 *
 * It pins the semantics that are easy to get subtly wrong: the tag union that
 * marks a container, the query-depth cap, the limit recursion where a
 * sub-trait rides its parent but a container contributes its children instead
 * of itself, the unfilled tail of a challenge track, an `ordered` container's
 * contents (the tag is the signal, and `order` has to sort with the unordered
 * remainder staying put), and the trait count at which the sheet drops the
 * trait-set layer for one flat list (B60).
 */

import {
  challengeRemaining,
  childrenOf,
  countSetPicks,
  countDescendants,
  hasContents,
  isContainer,
  isOpenContainer,
  isOrdered,
  orderedChildren,
  canPickUp,
  findSetting,
  groupRelationRows,
  relationContinuations,
  rootAnchor,
  showsChildren,
  sortSetTraits,
  subtreeContains,
  traitTags,
  usesFlatTraitList,
} from '../src/utils/traitTree.js'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}

console.log('\ntrait tree — tag union, depth cap, limit recursion\n')

// ── tag union (B116): either source can mark a container ────────────────
ok('registry tag marks a container', isContainer({ tags: [], registryTags: ['container'] }), true)
ok('instance tag marks a container', isContainer({ tags: ['container'], registryTags: [] }), true)
ok('no tag → not a container', isContainer({ tags: ['offensive'], registryTags: ['wood'] }), false)
ok('tags dedupe across both', traitTags({ tags: ['a'], registryTags: ['a', 'b'] }), ['a', 'b'])
ok('missing tags are tolerated', isContainer({}), false)

// ── children are read straight off the API's nesting ────────────────────
ok('childrenOf reads subTraitSettings', childrenOf({ subTraitSettings: [1, 2] }).length, 2)
ok('childrenOf tolerates no children', childrenOf({}).length, 0)
ok('childrenOf tolerates a null setting', childrenOf(null).length, 0)

// ── ordered contents: an author's tag, and a stable read of `order` ────
// The tag is the signal, not the presence of `order`: `order` is optional and
// almost nothing sets it (11 of 926 live sub-trait settings), so inferring the
// shape from it would let stray data entry re-lay-out a container.
const orderedBox = { tags: ['container', 'ordered'], subTraitSettings: [{ id: 'a' }] }
ok('ordered requires the container tag', isOrdered({ tags: ['ordered'] }), false)
ok('container + ordered is ordered', isOrdered(orderedBox), true)
ok('a plain container is not ordered', isOrdered({ tags: ['container'] }), false)
ok('ordered rides the registry tag too', isOrdered({ registryTags: ['container', 'ordered'] }), true)

const numbered = { subTraitSettings: [
  { id: 'c', order: 3 },
  { id: 'a', order: 1 },
  { id: 'loose' },
  { id: 'b', order: 2 },
  { id: 'loose2' },
] }
ok('orderedChildren sorts by order, unordered last, stable',
  orderedChildren(numbered).map((k) => k.id), ['a', 'b', 'c', 'loose', 'loose2'])
ok('with no order at all it returns the read order untouched',
  orderedChildren({ subTraitSettings: [{ id: 'x' }, { id: 'y' }] }).map((k) => k.id), ['x', 'y'])
ok('orderedChildren tolerates no children', orderedChildren({}).length, 0)

// ── the limit rule ──────────────────────────────────────────────────────
const pool = new Set(['rope', 'coin', 'sword', 'sharp'])
const isInPool = (t) => pool.has(t.id)
const tree = [
  { id: 'assets', tags: ['container'], subTraitSettings: [
    { id: 'rope', dice: ['D6'], subTraitSettings: [] },
    { id: 'pouch', tags: ['container'], subTraitSettings: [
      { id: 'coin', dice: ['D4'], subTraitSettings: [] },
      { id: 'empty-pouch', tags: ['container'], subTraitSettings: [] },
    ]},
    { id: 'knife', dice: ['D6'], subTraitSettings: [] },
  ]},
  { id: 'sword', dice: ['D8'], subTraitSettings: [
    { id: 'sharp', dice: ['D6'], subTraitSettings: [], fromType: 'traitsetting' },
  ]},
  { id: 'lonely', tags: ['container'], subTraitSettings: [] },
]

ok('container with two picks counts 2', countSetPicks([tree[0]], isInPool), 2)
ok('non-container rides its sub-trait → 1', countSetPicks([tree[1]], isInPool), 1)
ok('empty container costs nothing', countSetPicks([tree[2]], isInPool), 0)
ok('whole set', countSetPicks(tree, isInPool), 3)
ok('nothing in the pool is 0', countSetPicks([tree[0]], () => false), 0)
ok('contents count (all depths)', countDescendants(tree[0]), 5)
ok('contents count ignores siblings', countDescendants(tree[1]), 1)

// ── what a row reveals ──────────────────────────────────────────────────
const plainParent = { id: 'sword', subTraitSettings: [{ id: 'sharp' }] }
const containerRow = { id: 'pack', tags: ['container'], subTraitSettings: [{ id: 'rope' }] }
const emptyContainer = { id: 'pack2', tags: ['container'], subTraitSettings: [] }

ok('plain parent shows its children', showsChildren(plainParent), true)
ok('container is collapsed until opened', showsChildren(containerRow), false)
ok('opened container shows them', showsChildren(containerRow, { expanded: true }), true)
ok('childless container shows nothing', showsChildren(emptyContainer, { expanded: true }), false)
ok('a hidden row reveals nothing', showsChildren(plainParent, { rootKnown: false }), false)

// ── contents of a container, and a container inside a container ─────────
// The Iron Roots bug: `portents` (container) holds `portents` (container) holds
// `portents`. A row that is container contents hides its own sub-traits — but
// NOT when it is itself a container, because its row renders a disclosure and a
// chevron that opens nothing is a dead control.
const innerContainer = { id: 'inner', tags: ['container'], subTraitSettings: [{ id: 'deep', subTraitSettings: [] }] }
const innerPlain = { id: 'innerPlain', subTraitSettings: [{ id: 'deep2', subTraitSettings: [] }] }
ok('container contents hide their own sub-traits', showsChildren(innerPlain, { insideContainer: true }), false)
ok('…even when they are not containers and would otherwise show them',
   showsChildren(innerPlain), true)
ok('a container inside a container stays closed until opened',
   showsChildren(innerContainer, { insideContainer: true }), false)
ok('…and opens when it is, so its chevron is not a dead control',
   showsChildren(innerContainer, { insideContainer: true, expanded: true }), true)
ok('a nested container with nothing in it still shows nothing',
   showsChildren({ id: 'e', tags: ['container'], subTraitSettings: [] },
                 { insideContainer: true, expanded: true }), false)
ok('fog still wins over nesting',
   showsChildren(innerContainer, { insideContainer: true, expanded: true, rootKnown: false }), false)
ok('the Iron Roots shape is reachable at every level', (() => {
  const deep = { id: 'd2', tags: ['container'], subTraitSettings: [] }
  const mid = { id: 'd1', tags: ['container'], subTraitSettings: [deep] }
  const top = { id: 'd0', tags: ['container'], subTraitSettings: [mid] }
  // closed at the top
  if (showsChildren(top, {})) return 'top leaked'
  // opened at the top: the mid container appears, but stays closed
  if (!showsChildren(top, { expanded: true })) return 'top would not open'
  if (showsChildren(mid, { insideContainer: true })) return 'mid leaked while closed'
  // opened at the mid: the deepest row is finally reachable
  return showsChildren(mid, { insideContainer: true, expanded: true }) ? 'ok' : 'deep row unreachable'
})(), 'ok')

// ── only a container with something to disclose gets a control ──────────
ok('filled container earns a disclosure', hasContents(containerRow), true)
ok('empty container does not', hasContents(emptyContainer), false)
ok('a non-container never does', hasContents(plainParent), false)
ok('a container is still one while empty', isContainer(emptyContainer), true)

// ── "open" for arranging: expanded, or empty ────────────────────────────
ok('an empty container is open without being expanded', isOpenContainer(emptyContainer), true)
ok('a filled container is not open while collapsed', isOpenContainer(containerRow), false)
ok('…until it is expanded', isOpenContainer(containerRow, true), true)
ok('a non-container is never open', isOpenContainer(plainParent, true), false)

// ── where a row may be dropped: not itself, not inside itself ───────────
ok('a container contains itself', subtreeContains(tree[0], 'assets'), true)
ok('…its direct child', subtreeContains(tree[0], 'rope'), true)
ok('…and its grandchild', subtreeContains(tree[0], 'coin'), true)
ok('…but not a sibling', subtreeContains(tree[0], 'sword'), false)
ok('a leaf contains only itself', subtreeContains(tree[1], 'sharp'), true)
ok('…and nothing else', subtreeContains(tree[1], 'assets'), false)

// ── a container is draggable only into ANOTHER container ────────────────
// The rule the sheet applies per row: some open container that is neither this
// row nor anywhere inside it must be able to receive it.
const droppable = (t, open) => open.some((c) => c.id !== t.id && !subtreeContains(t, c.id))
ok('a trait can be dropped into an open container', droppable(tree[1], [tree[0]]), true)
ok('a container cannot be dropped into itself', droppable(tree[0], [tree[0]]), false)
ok('a container cannot be dropped into its own descendant',
   droppable(tree[0], [tree[0].subTraitSettings[1]]), false)
ok('a container can be dropped into an unrelated container',
   droppable(tree[0], [tree[1]]), true)
ok('nothing droppable with no open container', droppable(tree[0], []), false)

// ── finding a setting, and the anchor its chain resolves to ─────────────
ok('findSetting finds a root', findSetting(tree, 'sword')?.id, 'sword')
ok('findSetting finds a nested child', findSetting(tree, 'coin')?.id, 'coin')
ok('findSetting returns null when absent', findSetting(tree, 'nope'), null)

// A sub-trait carries no anchor, so un-nesting it must resolve the ROOT of its
// chain — otherwise a child of a morph container would come out ego.
const nested = [
  { id: 'ego-root', fromType: 'entity', subTraitSettings: [
    { id: 'ego-child', fromType: 'traitsetting', parentTraitsettingId: 'ego-root', subTraitSettings: [
      { id: 'ego-grandchild', fromType: 'traitsetting', parentTraitsettingId: 'ego-child', subTraitSettings: [] },
    ] },
  ] },
  { id: 'body-root', fromType: 'projection', projectionId: 'body-1', subTraitSettings: [
    { id: 'body-child', fromType: 'traitsetting', parentTraitsettingId: 'body-root', subTraitSettings: [] },
  ] },
]
ok('a root anchors itself', rootAnchor(nested, 'ego-root')?.id, 'ego-root')
ok('a child resolves to its root', rootAnchor(nested, 'ego-child')?.id, 'ego-root')
ok('…through two levels', rootAnchor(nested, 'ego-grandchild')?.id, 'ego-root')
ok('a morph chain resolves to its body', rootAnchor(nested, 'body-child')?.fromType, 'projection')
ok('…carrying the body id', rootAnchor(nested, 'body-child')?.projectionId, 'body-1')
ok('an unknown id has no anchor', rootAnchor(nested, 'nope'), null)

// ── which rows can be picked up ─────────────────────────────────────────
// Two kinds: a root trait, and a trait sitting inside a container AT ANY DEPTH.
// What separates them from everything else is the **parent** — a sub-trait of a
// non-container is part of it and never moves, however deep it sits. Both kinds
// still need somewhere to go.
ok('a root trait with a destination can be picked up',
   canPickUp({ depth: 0, hasDestination: true }), true)
ok('a root trait with nowhere to go cannot',
   canPickUp({ depth: 0, hasDestination: false }), false)
ok('a trait directly inside a container can',
   canPickUp({ depth: 1, insideContainer: true, hasDestination: true }), true)
ok('…but not when nothing can receive it',
   canPickUp({ depth: 1, insideContainer: true, hasDestination: false }), false)
ok('a sub-trait of a NON-container cannot',
   canPickUp({ depth: 1, insideContainer: false, hasDestination: true }), false)

// The Iron Roots case: portents > portents > portents. The third level sits in a
// container, so it is pickable — this used to be false, and the row had no grip.
ok('a sub-trait of a sub-trait INSIDE a container can (Iron Roots)',
   canPickUp({ depth: 2, insideContainer: true, hasDestination: true }), true)
ok('…and one level deeper still can',
   canPickUp({ depth: 3, insideContainer: true, hasDestination: true }), true)
ok('a deep sub-trait of a non-container still cannot',
   canPickUp({ depth: 2, insideContainer: false, hasDestination: true }), false)
ok('depth stops mattering once the parent is a container', (() => {
  const at = (d) => canPickUp({ depth: d, insideContainer: true, hasDestination: true })
  return [1, 2, 3, 4, 9].every(at)
})(), true)

// ── a container is still a container when marked on the registry side ────
ok('nested container detected via registryTags',
   isContainer(tree[0].subTraitSettings[1]), true)
ok('deeper nesting is reachable', childrenOf(tree[0].subTraitSettings[1]).length, 2)

// ── a challenge track draws its unfilled capacity as ghost dice ──────────
// The filled dice ARE the ledger (`dice`); the shortfall is the tail of the
// capacity array, and it keeps its own slot types — a d6 can fill a d8 slot,
// and the two lists must not be paired.
const track = (dice, capacity) => ({ ratingType: 'CHALLENGE', dice, capacity })
ok('4 filled of 6 leaves the last 2 capacity dice',
   challengeRemaining(track(['d8', 'd8', 'd8', 'd8'], ['d8', 'd8', 'd8', 'd8', 'd8', 'd8'])), ['d8', 'd8'])
ok('an empty track leaves the whole capacity',
   challengeRemaining(track([], ['d6', 'd6', 'd6'])), ['d6', 'd6', 'd6'])
ok('a full track leaves none',
   challengeRemaining(track(['d6', 'd6'], ['d6', 'd6'])), [])
ok('an over-filled track leaves none (never invents dice)',
   challengeRemaining(track(['d6', 'd6', 'd6'], ['d6', 'd6'])), [])
ok('a mixed capacity keeps its own slot types, in order',
   challengeRemaining(track(['d4'], ['d4', 'd4', 'd6'])), ['d4', 'd6'])
ok('no capacity set, no ghosts',
   challengeRemaining(track(['d6'], null)), [])
ok('a non-challenge trait has no track',
   challengeRemaining({ ratingType: 'STATIC', dice: ['d6'], capacity: ['d8'] }), [])

// ── a set's list puts its containers last ───────────────────────────────
// Containers hold rather than act, so they sit under the playable traits. The
// sort is stable: each group keeps the order the query returned.
const tPlain1 = { id: 'p1', tags: [] }
const tPlain2 = { id: 'p2', tags: [] }
const tBox1 = { id: 'c1', tags: ['container'] }
const tBox2 = { id: 'c2', tags: ['container'] }
ok('containers move to the bottom',
   sortSetTraits([tBox1, tPlain1, tBox2, tPlain2]).map(t => t.id), ['p1', 'p2', 'c1', 'c2'])
ok('each group keeps its order',
   sortSetTraits([tPlain2, tPlain1]).map(t => t.id), ['p2', 'p1'])
ok('a registry-tagged container counts as one',
   sortSetTraits([{ id: 'reg', registryTags: ['container'] }, tPlain1]).map(t => t.id), ['p1', 'reg'])
ok('a list with no containers is untouched',
   sortSetTraits([tPlain1, tPlain2]).map(t => t.id), ['p1', 'p2'])
ok('an absent list is fine', sortSetTraits(undefined), [])

// ── and ego before morph, with containers still under both ──────────────
const tEgo = { id: 'e1', ego: true, tags: [] }
const tMorph = { id: 'm1', ego: false, tags: [] }
ok('ego before morph',
   sortSetTraits([tMorph, tEgo]).map(t => t.id), ['e1', 'm1'])
ok('containers stay under both',
   sortSetTraits([tBox1, tMorph, tEgo]).map(t => t.id), ['e1', 'm1', 'c1'])
ok('an ego container outranks a morph one',
   sortSetTraits([{ id: 'cm', tags: ['container'], ego: false },
                  { id: 'ce', tags: ['container'], ego: true },
                  tEgo]).map(t => t.id), ['e1', 'ce', 'cm'])
ok('a missing ego flag reads as ego',
   sortSetTraits([{ id: 'x' }, tMorph]).map(t => t.id), ['x', 'm1'])
ok('ego/morph does not disturb the order inside a group',
   sortSetTraits([{ id: 'e2', ego: true }, { id: 'e1', ego: true }]).map(t => t.id), ['e2', 'e1'])

// ── B60: a low-trait sheet skips the trait-set layer ────────────────────
// The count is the traits the Traits tab would list — the roots of the sets.
// Profile traits are a separate tab and never reach `traitSets`, so they cannot
// move this threshold; nested sub-traits ride their parent and do not count.
const setOf = (name, n) => ({ name, traits: Array.from({ length: n }, (_, i) => ({ id: `${name}-${i}` })) })
ok('no traits at all → flat', usesFlatTraitList([]), true)
ok('one short set → flat', usesFlatTraitList([setOf('a', 3)]), true)
ok('exactly at the limit → flat', usesFlatTraitList([setOf('a', 12)]), true)
ok('one over the limit → split', usesFlatTraitList([setOf('a', 13)]), false)
ok('the limit is the total across sets, not per set',
   usesFlatTraitList([setOf('a', 6), setOf('b', 6)]), true)
ok('one more across two sets tips it over',
   usesFlatTraitList([setOf('a', 6), setOf('b', 7)]), false)
ok('a sub-trait does not count — it rides its parent',
   usesFlatTraitList([{ name: 'a', traits: [
     { id: 'p', subTraitSettings: Array.from({ length: 20 }, (_, i) => ({ id: `c${i}` })) },
   ] }]), true)
ok('an absent list is flat rather than a crash', usesFlatTraitList(undefined), true)
ok('the limit is overridable', usesFlatTraitList([setOf('a', 5)], 4), false)

// ── `→ contact` repeats only when the relationship changes ──────────────
// Consecutive rows about one relationship read as a group; the label belongs at
// the top of it, not on every line (the Blue Book's `entryContinuations` rule).
const rel = (id, contactId, contactName, type = 'relation') => ({
  id, fromType: 'relationship', relationshipContactId: contactId,
  relationshipContactName: contactName, relationshipType: type,
})
const plain = (id) => ({ id, fromType: 'entity' })

ok('a lone relationship states its contact',
   [...relationContinuations([rel('a', 'gmc-1', 'Bai')])], [])
ok('the second row about the same relationship does not repeat it',
   [...relationContinuations([rel('a', 'gmc-1', 'Bai'), rel('b', 'gmc-1', 'Bai')])], ['b'])
ok('a third row is a continuation too',
   [...relationContinuations([rel('a', 'gmc-1', 'Bai'), rel('b', 'gmc-1', 'Bai'), rel('c', 'gmc-1', 'Bai')])],
   ['b', 'c'])
ok('a different contact starts a new group',
   [...relationContinuations([rel('a', 'gmc-1', 'Bai'), rel('b', 'gmc-2', 'Dvalov')])], [])
ok('and the row after it continues that new group',
   [...relationContinuations([rel('a', 'gmc-1', 'Bai'), rel('b', 'gmc-2', 'Dvalov'), rel('c', 'gmc-2', 'Dvalov')])],
   ['c'])
ok('an ordinary trait between two breaks the run',
   [...relationContinuations([rel('a', 'gmc-1', 'Bai'), plain('x'), rel('c', 'gmc-1', 'Bai')])], [])
ok('two ordinary traits are never continuations',
   [...relationContinuations([plain('a'), plain('b')])], [])
ok('the same contact through a different edge type is a different relationship',
   [...relationContinuations([rel('a', 'f-1', 'Iron Roots', 'membership'), rel('b', 'f-1', 'Iron Roots', 'relation')])], [])
ok('a row with no contact id never matches',
   [...relationContinuations([rel('a', null, ''), rel('b', null, '')])], [])
ok('an absent list is empty rather than a crash', [...relationContinuations(undefined)], [])
ok('a single row is empty rather than a crash', [...relationContinuations([rel('a', 'gmc-1', 'Bai')])], [])

// ── a relationship's rows are consecutive ──────────────────────────────
const keys = (rows) => rows.map(r => r.id)
const A1 = rel('a1', 'gmc-1', 'Bai'), A2 = rel('a2', 'gmc-1', 'Bai')
const B1 = rel('b1', 'gmc-2', 'Dvalov'), B2 = rel('b2', 'gmc-2', 'Dvalov')
const X = plain('x')

ok('a split group is pulled together, keeping first-appearance order',
   keys(groupRelationRows([A1, B1, A2])), ['a1', 'a2', 'b1'])
ok('two groups each keep their own rows',
   keys(groupRelationRows([A1, B1, A2, B2])), ['a1', 'a2', 'b1', 'b2'])
ok('already-grouped rows are left alone (the no-op case)',
   keys(groupRelationRows([A1, A2, B1, B2])), ['a1', 'a2', 'b1', 'b2'])
ok('an ordinary trait keeps its own place between groups',
   keys(groupRelationRows([A1, X, B1, A2])), ['a1', 'a2', 'x', 'b1'])
ok('ordinary traits never group with each other',
   keys(groupRelationRows([plain('p'), plain('q')])), ['p', 'q'])
ok('a different edge type is a different group',
   keys(groupRelationRows([rel('a', 'f-1', 'Iron Roots', 'membership'),
                           rel('b', 'f-1', 'Iron Roots', 'relation')])), ['a', 'b'])
ok('an absent list is empty rather than a crash', keys(groupRelationRows(undefined)), [])
ok('a single row survives', keys(groupRelationRows([A1])), ['a1'])

// The two together: grouped, then labelled once.
ok('after grouping, only the first row of the run states the contact',
   [...relationContinuations(groupRelationRows([A1, B1, A2]))], ['a2'])

console.log(`\n  ${pass} passed, ${fail} failed\n`)
process.exit(fail ? 1 : 0)
