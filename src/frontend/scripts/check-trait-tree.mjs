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
 * marks a container, the query-depth cap, and the limit recursion where a
 * sub-trait rides its parent but a container contributes its children instead
 * of itself.
 */

import {
  childrenOf,
  countSetPicks,
  countDescendants,
  hasContents,
  isContainer,
  isOpenContainer,
  findSetting,
  rootAnchor,
  showsChildren,
  subtreeContains,
  traitTags,
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

// ── a container is still a container when marked on the registry side ────
ok('nested container detected via registryTags',
   isContainer(tree[0].subTraitSettings[1]), true)
ok('deeper nesting is reachable', childrenOf(tree[0].subTraitSettings[1]).length, 2)

console.log(`\n  ${pass} passed, ${fail} failed\n`)
process.exit(fail ? 1 : 0)
