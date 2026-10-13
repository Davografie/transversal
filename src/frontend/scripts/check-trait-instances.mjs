/**
 * Executable check for the trait-instances panel.
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image, the same
 * way as the other checks:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-trait-instances.mjs
 *
 * The ask: *"open a child panel from a trait that shows all the instances of that
 * trait… I want to see who the trait belongs to (entity or projection from,
 * relationship between who, sub-trait on which super-trait)… similar
 * functionality to the batch edit traits from the trait set, so batch edit trait
 * instances. I need to clean up/straighten out a lot of traits that came over
 * from the migration."*
 *
 * Two halves, and only one of them can be run here:
 *
 *  - the **host wording and the filter predicate** are pure functions in
 *    `utils/traitInstanceHost.js`, so this script *runs* them (a fake, and the
 *    four kinds, rather than a restatement of them);
 *  - the **read** is the API's `traitInstances(traitId)` — that it resolves all
 *    four anchors against real rows is the backend suite's and e2e's to show.
 */
import { readFileSync } from 'node:fs'

import {
  HOST_KINDS, hostDetail, hostKindLabel, hostLine, hostTypeBadge,
  instanceMatches, kindCounts, sortInstances,
} from '../src/utils/traitInstanceHost.js'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}
const yes = (name, got) => ok(name, !!got, true)

const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8')
const PANEL = read('../src/components/gm/GmTraitInstancesPanel.vue')
const COMPOSABLE = read('../src/composables/useTraitInstances.js')
const EDITOR = read('../src/components/gm/GmTraitEditPanel.vue')
const REGISTRY = read('../src/constants/restorablePanels.js')

const host = (kind, extra = {}) => ({
  kind, entityId: 'e1', entityName: 'Kael Drift', entityType: 'CHARACTER',
  universe: '', aboutId: '', aboutName: '', aboutType: '', relationshipType: '',
  parentTraitsettingId: '', parentTraitId: '', parentTraitName: '', ...extra,
})
const inst = (hostObj, extra = {}) => ({
  id: 'ts-1', traitId: 'trait-x', ratingType: 'STATIC', dice: ['D8'],
  polarity: 'POSITIVE', statement: '', notes: '', tags: [], enabled: true,
  host: hostObj, ...extra,
})

// ── 1. who owns it, in the four kinds ───────────────────────────────────
console.log('\nthe host line says who owns the instance\n')

ok('an entity instance is the entity', hostLine(host('entity')), 'Kael Drift')
ok('  …and its type is the badge', [hostDetail(host('entity')), hostTypeBadge(host('entity'))],
  ['CHARACTER', 'CHARACTER'])
ok('a body instance names the entity it projects FROM, not the body',
  hostLine(host('projection', { universe: 'three_realms' })), 'Kael Drift')
ok('  …and the universe it stands in is the detail',
  hostDetail(host('projection', { universe: 'three_realms' })), 'in three_realms')
ok('  …with the universe instead of a type badge (both would be noise)',
  hostTypeBadge(host('projection', { universe: 'three_realms' })), '')
ok('a relationship instance is "holder → about"',
  hostLine(host('relationship', { aboutName: 'The Azure Dawn Sect', relationshipType: 'relation' })),
  'Kael Drift → The Azure Dawn Sect')
ok('  …and its edge type is the detail',
  hostDetail(host('relationship', { aboutName: 'X', relationshipType: 'relation' })), 'relation')
ok('a sub-trait instance hangs off the root entity',
  hostLine(host('traitsetting', { parentTraitName: 'portents' })), 'Kael Drift')
ok('  …and names the super-trait above it',
  hostDetail(host('traitsetting', { parentTraitName: 'portents' })), 'under portents')
ok('a sub-trait with no readable parent still says what it is',
  hostDetail(host('traitsetting', { parentTraitName: '' })), 'sub-trait')
ok('a missing host does not render as blank', hostLine(null), '(unknown host)')
ok('an instance whose entity is gone says so', hostLine(host('entity', { entityName: '' })), '(missing entity)')
ok('a relationship with a gone party still names the holder',
  hostLine(host('relationship', { aboutName: '' })), 'Kael Drift → (gone)')
ok('the four kinds are labelled', HOST_KINDS.map(hostKindLabel),
  ['Entity', 'Body', 'Relationship', 'Sub-trait'])
ok('an unknown kind reads as an entity rather than as nothing', hostKindLabel('nonsense'), 'Entity')

// ── 2. the filter predicate ─────────────────────────────────────────────
// One predicate for the count, the "select all matching" and the drawn rows, so
// they cannot disagree about what "matching" means.
console.log('\nwhat the filter bar matches\n')

const onBody = inst(host('projection', { entityName: 'jeffrey', universe: 'three_realms' }),
  { id: 'ts-body', statement: '16', tags: ['migrated'] })
const onRel = inst(host('relationship', { entityName: 'Elder Zhu', aboutName: 'The Azure Dawn Sect' }),
  { id: 'ts-rel', ratingType: 'CHALLENGE', dice: ['D10'], polarity: 'NEGATIVE', enabled: false })
const onSub = inst(host('traitsetting', { entityName: 'Iron Roots', entityType: 'FACTION', parentTraitName: 'portents' }),
  { id: 'ts-sub', statement: 'the forge-fires' })
const all = [onBody, onRel, onSub]

ok('no filters matches everything', all.filter((i) => instanceMatches(i, {})).length, 3)
ok('by anchor kind', all.filter((i) => instanceMatches(i, { kind: 'projection' })).map((i) => i.id), ['ts-body'])
ok('by rating type', all.filter((i) => instanceMatches(i, { ratingType: 'CHALLENGE' })).map((i) => i.id), ['ts-rel'])
ok('by polarity', all.filter((i) => instanceMatches(i, { polarity: 'NEGATIVE' })).map((i) => i.id), ['ts-rel'])
ok('by die — a die anywhere in the pool counts',
  all.filter((i) => instanceMatches(i, { die: 'D10' })).map((i) => i.id), ['ts-rel'])
ok('enabled=yes', all.filter((i) => instanceMatches(i, { enabled: 'yes' })).map((i) => i.id), ['ts-body', 'ts-sub'])
ok('enabled=no', all.filter((i) => instanceMatches(i, { enabled: 'no' })).map((i) => i.id), ['ts-rel'])
ok('the search reaches the owner', all.filter((i) => instanceMatches(i, { q: 'jeffrey' })).map((i) => i.id), ['ts-body'])
ok('  …the entity type', all.filter((i) => instanceMatches(i, { q: 'faction' })).map((i) => i.id), ['ts-sub'])
ok('  …the relationship subject', all.filter((i) => instanceMatches(i, { q: 'azure' })).map((i) => i.id), ['ts-rel'])
ok('  …the super-trait', all.filter((i) => instanceMatches(i, { q: 'portent' })).map((i) => i.id), ['ts-sub'])
ok('  …the statement', all.filter((i) => instanceMatches(i, { q: 'forge' })).map((i) => i.id), ['ts-sub'])
ok('  …a tag', all.filter((i) => instanceMatches(i, { q: 'migrated' })).map((i) => i.id), ['ts-body'])
ok('  …the id', all.filter((i) => instanceMatches(i, { q: 'ts-rel' })).map((i) => i.id), ['ts-rel'])
ok('  …and is case-insensitive', all.filter((i) => instanceMatches(i, { q: 'ELDER' })).map((i) => i.id), ['ts-rel'])
ok('filters combine', all.filter((i) => instanceMatches(i, { kind: 'relationship', q: 'zhu' })).map((i) => i.id), ['ts-rel'])
ok('a host-less instance is still findable by its own fields',
  instanceMatches(inst(null, { statement: 'orphan', host: null }), { q: 'orphan' }), true)

// ── 3. ordering and counts ──────────────────────────────────────────────
console.log('\nthe list is grouped by kind\n')

ok('kinds come in a stable order, then by owner',
  sortInstances([onSub, onRel, onBody, inst(host('entity', { entityName: 'Aaa' }))])
    .map((i) => i.host.kind),
  ['entity', 'projection', 'relationship', 'traitsetting'])
ok('within a kind, by owner name',
  sortInstances([inst(host('entity', { entityName: 'Zed' }), { id: 'z' }),
                 inst(host('entity', { entityName: 'Abe' }), { id: 'a' })])
    .map((i) => i.id),
  ['a', 'z'])
{
  const input = [onSub, onRel]
  sortInstances(input)
  ok('sorting does not mutate the caller\'s list', input.map((i) => i.id), ['ts-sub', 'ts-rel'])
}
ok('counts per kind — the summary line and the chips read the same',
  kindCounts([...all, inst(host('entity'))]), { entity: 1, projection: 1, relationship: 1, traitsetting: 1 })
ok('an empty list counts zero rather than missing keys', kindCounts([]),
  { entity: 0, projection: 0, relationship: 0, traitsetting: 0 })

// ── 4. the panel does not re-word the host itself ───────────────────────
console.log('\nthe panel reads the shared wording\n')

yes('the panel imports the host wording rather than writing its own',
  /from '@\/utils\/traitInstanceHost\.js'/.test(PANEL)
  && /hostLine\(/.test(PANEL) && /hostDetail\(/.test(PANEL)
  && /instanceMatches\(/.test(PANEL) && /sortInstances\(/.test(PANEL))
ok('no second copy of the arrow wording', /→/.test(PANEL.replace(/<[^>]*>/g, '')), false)

// ── 5. the read, and the bounded fan-out ────────────────────────────────
console.log('\nthe read and the writes\n')

yes('the read is the inverse query, asking for the host block',
  /traitInstances\(traitId: \$id\)/.test(COMPOSABLE) && /host \{/.test(COMPOSABLE))
for (const field of ['kind', 'entityName', 'entityType', 'universe', 'aboutName',
  'relationshipType', 'parentTraitName']) {
  yes(`  …including host.${field}`, COMPOSABLE.includes(field))
}
yes('only the missing keys are written, so a field left alone is left alone',
  /const input = \{ \.\.\.changes \}/.test(COMPOSABLE))
yes('a bulk edit is one updateTraitSetting per instance',
  /updateTraitSetting\(id: \$id, input: \$input\)/.test(COMPOSABLE))
yes('and a bulk remove is removeTraitSetting',
  /removeTraitSetting\(id: \$id\)/.test(COMPOSABLE))
// 547 instances exist for one trait today: an unbounded fan-out would put 500
// concurrent writes on the API.
yes('the fan-out is bounded, not Promise.all over every id',
  /const CONCURRENCY = \d+/.test(COMPOSABLE) && !/Promise\.all\(\s*ids\.map/.test(COMPOSABLE))
yes('  …and a failed write is reported rather than aborting the run',
  /failed\.push\(id\)/.test(COMPOSABLE) && /succeeded\.push\(id\)/.test(COMPOSABLE))

// ── 6. the panel's own behaviour ────────────────────────────────────────
console.log('\nthe panel\n')

yes('it refetches after a write, so the list is what the server has',
  (PANEL.match(/await fetchInstances\(props\.traitId\)/g) || []).length >= 2)
yes('the selection survives a partial failure — only the failures stay selected',
  /selectedIds\.value = failed/.test(PANEL))
yes('a bulk remove asks first', /confirmingRemove/.test(PANEL) && /Really remove/.test(PANEL))
yes('"select all matching" works on the filtered set', /function toggleAllMatching/.test(PANEL)
  && /shown\.value\.forEach/.test(PANEL))
yes('the dice action can clear dice (the migration\'s stray d4s)',
  /apply\.dice === 'CLEAR'/.test(PANEL) && /changes\.dice = \[\]/.test(PANEL))
yes('and setting a die is one die, as the definition editor sets a default',
  /changes\.dice = \[apply\.dice\]/.test(PANEL))

// ── 7. opening it, from a trait ─────────────────────────────────────────
console.log('\nopening it from the trait\n')

yes('the trait editor has the Instances section',
  /ps-section-title">Instances</.test(EDITOR) && /Open instances…/.test(EDITOR))
yes('which opens the panel as a child of the trait editor',
  /component: GmTraitInstancesPanel/.test(EDITOR) && /panel\.open\(\{/.test(EDITOR))
yes('keyed by trait, so two traits get two panels and a re-open replaces its own',
  /id: `trait-instances:\$\{trait\.value\.id\}`/.test(EDITOR))
yes('passing the definition it is about', /traitId: trait\.value\.id/.test(EDITOR)
  && /traitName: trait\.value\.name/.test(EDITOR))
ok('with no badge — the badge is the copy-ID control and this id is a composite',
  /badge: .*trait-instances/.test(EDITOR), false)
yes('the panel is restorable: its whole spec is props and it reads its own data',
  /^\s*GmTraitInstancesPanel,$/m.test(REGISTRY))

console.log(`\n${pass} passed, ${fail} failed\n`)
process.exit(fail ? 1 : 0)
