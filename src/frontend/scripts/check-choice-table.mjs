/**
 * Executable check for the choice table's row vocabulary ([[UI-UX Design#Choice table]]).
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Mount over `/app` (not `/work`) so the
 * image's `node_modules` still resolves `vue`:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-choice-table.mjs
 *
 * It pins two things that would otherwise fail *silently*:
 *
 *  1. the row vocabulary — the scheme owns the key column, and a condition or an
 *     effect is phrased through the one resolver rather than rendered raw;
 *  2. the name-resolution contract, as shipped text: the shared resolver reads
 *     traits by **traitset**, not by universe. The bug it replaces was invisible
 *     in review — `LifePathWizard` resolved traits from `traitsByUniverse` and
 *     `trait-rel-tenure` (stamped `universes: ["earth"]`) rendered as a raw id
 *     inside a `three_realms` path. A re-introduced per-universe read has to fail
 *     here, so the assertion is on the shipped source and not on a paraphrase.
 */

import { readFileSync } from 'node:fs'
import { conditionSummary, costSummary, effectSummary, entryKey } from '../src/utils/rowSummary.js'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  if (same) pass++
  else { fail++; console.error(`FAIL ${name}\n  got  ${JSON.stringify(got)}\n  want ${JSON.stringify(want)}`) }
}
const yes = (name, cond, detail = '') => ok(name + (cond ? '' : ` ${detail}`), !!cond, true)

// ── the key column belongs to the scheme, not the row ────────────────────────
console.log('\nrow vocabulary — the key column\n')
{
  const range = { minValue: 3, maxValue: 5, tier: 'SUCCESS' }
  const index = { label: 'third' }
  const tier = { tier: 'EXCEPTIONAL' }
  const weight = { weight: 7 }

  ok('RANGE shows the band', entryKey(range, 0, 'RANGE'), '3–5')
  ok('INDEX shows the position (1-based)', entryKey(index, 2, 'INDEX'), '3')
  ok('TIER shows the tier', entryKey(tier, 0, 'TIER'), 'EXCEPTIONAL')
  ok('WEIGHT shows w', entryKey(weight, 0, 'WEIGHT'), 'w7')

  // One row can carry several key shapes; the scheme decides which is the key.
  ok('the same row reads differently per scheme — RANGE', entryKey(range, 0, 'RANGE'), '3–5')
  ok('the same row reads differently per scheme — TIER', entryKey(range, 0, 'TIER'), 'SUCCESS')
  ok('the same row reads differently per scheme — INDEX', entryKey(range, 0, 'INDEX'), '1')

  // No scheme (an authoring list, an archetype list): read the row, then fall
  // back to position — never invent a key.
  ok('no scheme reads the row (tier)', entryKey(tier, 4, ''), 'EXCEPTIONAL')
  ok('no scheme reads the row (weight)', entryKey(weight, 4, ''), 'w7')
  ok('no scheme reads the row (band)', entryKey({ minValue: 1, maxValue: 2 }, 4, ''), '1–2')
  ok('nothing to read falls back to position', entryKey({ label: 'x' }, 4, ''), '5')
  // A row can carry several shapes at once; with no scheme the documented order
  // is tier → weight → band → position, so the reviewable behaviour is pinned
  // rather than left to whichever branch happens to come first.
  ok('with no scheme the order is tier → weight → band → position',
    [entryKey(range, 0, ''), entryKey({ weight: 2, minValue: 1, maxValue: 3 }, 0, ''), entryKey({ minValue: 1, maxValue: 3 }, 0, '')],
    ['SUCCESS', 'w2', '1–3'])
  ok('a WEIGHT row with no weight falls back to position', entryKey({}, 1, 'WEIGHT'), '2')
  // A partial band must not render "3–undefined".
  ok('a half-open band does not print undefined', entryKey({ minValue: 3 }, 0, 'RANGE'), '3–')
  ok('an empty entry is safe', entryKey(null, 0, 'RANGE'), '1')
}

// ── conditions are phrased, and through the supplied resolver ────────────────
console.log('\nrow vocabulary — conditions\n')
{
  const resolve = (id) => ({ 'trait-rel-tenure': 'tenure', 'ts-rel': 'relations', 'loc-iron': 'Iron Roots', earth: 'Earth' }[id] || id)

  ok('has_trait names the trait',
    conditionSummary({ type: 'has_trait', target: 'trait-rel-tenure' }, resolve), 'has tenure')
  ok('has_effective_trait says enabled',
    conditionSummary({ type: 'has_effective_trait', target: 'trait-rel-tenure' }, resolve), 'has tenure enabled')
  ok('has_trait_in_traitset names the set',
    conditionSummary({ type: 'has_trait_in_traitset', target: 'ts-rel' }, resolve), 'has a relations trait')
  ok('at_location names the place',
    conditionSummary({ type: 'at_location', target: 'loc-iron' }, resolve), 'at Iron Roots')
  ok('has_razmerit renders the comparator',
    conditionSummary({ type: 'has_razmerit', operator: '>=', value: '3' }, resolve), 'razmerit ≥ 3')
  ok('in_universe names the universe',
    conditionSummary({ type: 'in_universe', target: 'earth' }, resolve), 'in Earth')
  ok('an enum filter reads as "or" and resolves every value',
    conditionSummary({ type: 'in_universe', targets: ['earth', 'three_realms'] }, resolve), 'in Earth or three_realms')
  ok('trait_rating renders the threshold',
    conditionSummary({ type: 'trait_rating', target: 'trait-rel-tenure', value: 'd8' }, resolve), 'tenure d8')
  ok('a server phrase wins over re-phrasing',
    conditionSummary({ type: 'has_trait', target: 'trait-rel-tenure', phrase: 'needs tenure' }, resolve), 'needs tenure')
  ok('narrative is used where there is no structure',
    conditionSummary({ type: 'narrative', narrative: 'the moon is up' }, resolve), 'the moon is up')
  ok('an unknown type degrades to words, not to an id-only string',
    conditionSummary({ type: 'weird_gate', target: 'trait-rel-tenure' }, resolve), 'weird gate tenure')

  // The resolver is optional, and an unresolved id stays an id: the *resolver*
  // owns the fallback, so this function can never invent a different one.
  ok('with no resolver the id is left alone',
    conditionSummary({ type: 'has_trait', target: 'trait-rel-tenure' }), 'has trait-rel-tenure')
  ok('a resolver that misses leaves the id alone',
    conditionSummary({ type: 'has_trait', target: 'trait-nope' }, (x) => x), 'has trait-nope')
  ok('a plain string condition passes through', conditionSummary('always', resolve), 'always')
  ok('null is empty, not "undefined"', conditionSummary(null, resolve), '')
}

// ── effects ─────────────────────────────────────────────────────────────────
console.log('\nrow vocabulary — effects\n')
{
  const resolve = (id) => ({ 'trait-rel-rank': 'rank' }[id] || id)
  const labelFor = (e) => (e.type === 'step_up' ? 'Step Up Die' : `${e.type}/${e.action}`)

  ok('an effect names its action and target',
    effectSummary({ type: 'step_up', action: 'die', target: 'trait-rel-rank', result: 'd8' }, { labelFor, resolve }),
    'Step Up Die → rank (d8)')
  ok('self is not printed as a target',
    effectSummary({ type: 'step_up', action: 'die', target: 'self' }, { labelFor, resolve }), 'Step Up Die')
  ok('the source-trait token is not printed as a target',
    effectSummary({ type: 'step_up', action: 'die', target: '{source_trait}' }, { labelFor, resolve }), 'Step Up Die')
  ok('without a catalogue the raw pair is the label',
    effectSummary({ type: 'grant', action: 'trait', target: 'trait-rel-rank' }, { resolve }),
    'grant/trait → rank')
  ok('null is empty', effectSummary(null, {}), '')
}

// ── cost, and "free" being a real state rather than an empty string ─────────
console.log('\nrow vocabulary — cost\n')
{
  const summarize = (e) => `${e.action} ${e.target}`
  const paid = costSummary([
    { type: 'transfer_razmerit', action: 'spend', result: '2' },
    { type: 'grant', action: 'trait', target: 'trait-rel-rank' },
  ], summarize)
  ok('razmerit leads the cost cell', paid.label, '2 razmerit · trait trait-rel-rank')
  ok('the razmerit number is exposed for gating', paid.razmerit, 2)
  ok('a paid entry is not free', paid.free, false)

  ok('no costs reads as free', costSummary([], summarize), { label: '', razmerit: 0, free: true })
  ok('a non-razmerit cost is still a cost',
    costSummary([{ type: 'grant', action: 'trait', target: 'x' }], summarize).label, 'trait x')
  ok('a malformed razmerit spend cannot become NaN',
    costSummary([{ type: 'transfer_razmerit', action: 'spend', result: 'abc' }], summarize).label, '')
}

// ── the name-resolution contract, as shipped text ────────────────────────────
console.log('\nthe one resolver\n')
{
  // Comments are stripped first: these files *explain* the universe-scoped read
  // they replaced, and a guard that fails on its own explanation is a guard
  // nobody can keep.
  const code = (path) => readFileSync(path, 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')

  const resolver = code('src/composables/useLabelResolver.js')
  yes('the shared resolver reads traits by traitset (registry-wide)',
    /traitsByTraitsets/.test(resolver))
  yes('…and does not scope the trait map to one universe',
    !/traitsByUniverse/.test(resolver))
  yes('…so a host cannot reintroduce the universe-scoped read here',
    !/traitsByUniverse/.test(code('src/utils/rowSummary.js')))

  // The surface that shipped the defect must not carry its own map again.
  const wizard = code('src/components/LifePathWizard.vue')
  yes('the life-path wizard carries no trait-name map of its own',
    !/traitsByUniverse/.test(wizard) && !/traitNames/.test(wizard))
  yes('…and renders its step on the shared surface', /ChoiceTable/.test(wizard))

  const table = readFileSync('src/components/ui/ChoiceTable.vue', 'utf8')
  yes('the surface phrases conditions and effects through the resolver',
    /labels\.value\.condition\(/.test(table) && /labels\.value\.effect\(/.test(table))
  yes('the surface is a container, so it adapts to the room it has, not the window',
    /container-type:\s*inline-size/.test(table) && /@container ct/.test(table))
  yes('the legend is hidden once the columns collapse',
    /@container ct \(max-width: 520px\)\s*\{\s*\.ct-head\s*\{\s*display:\s*none/.test(table))
  yes('entrance motion is opt-out for reduced motion',
    /prefers-reduced-motion/.test(table))

  // One row engine: EntryPicker must delegate rather than keep its own rows.
  const picker = readFileSync('src/components/ui/EntryPicker.vue', 'utf8')
  yes('EntryPicker is an adapter over the surface', /ChoiceTable/.test(picker))
  yes('…and no longer carries its own row CSS', !/\.ep-row\s*\{/.test(picker))
}

console.log(fail ? `\n  ${fail} failed, ${pass} passed\n` : `\n  all ${pass} assertions pass\n`)
process.exit(fail ? 1 : 0)
