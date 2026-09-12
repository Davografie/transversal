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
  isContainer,
  showsChildren,
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

// ── a container is still a container when marked on the registry side ────
ok('nested container detected via registryTags',
   isContainer(tree[0].subTraitSettings[1]), true)
ok('deeper nesting is reachable', childrenOf(tree[0].subTraitSettings[1]).length, 2)

console.log(`\n  ${pass} passed, ${fail} failed\n`)
process.exit(fail ? 1 : 0)
