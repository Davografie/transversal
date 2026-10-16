/**
 * Executable check for the effect form's variable lists ([[B306]]).
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image, the same
 * way as the other checks:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-effect-variables.mjs
 *
 * What a green build cannot see:
 *
 * 1. **Which names the die picker offers.** The handler parses the substituted
 *    value as a die, so offering a name bound to anything else promises a value
 *    that lands a trait-instance id where a rating belongs — and offering a
 *    `many` name promises a value the engine refuses to substitute at all. The
 *    activation's own names were the *only* ones offered, so a rule's declared
 *    bound variables were invisible beside every path builder that offered them.
 * 2. **That the form still uses it.** The rule lives in a composable precisely so
 *    it can be run here; an un-wired import would leave the rule green and the
 *    screen wrong, which is the failure mode this file exists for.
 *
 * The case is the author's own: `sfx-cast-array` on the Global server, trigger
 * `manual`, source `trait_setting`, one declared variable
 * `formation_rating = select source → navigate rating dice` (element
 * `rating_die`, cardinality `many`).
 */
import { readFileSync } from 'node:fs'
import {
  chipVariablesFor,
  dieVariablesFor,
  scopeEntries,
} from '../src/composables/effectScopeVariables.js'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}
const no = (name, cond, detail = '') => {
  cond ? pass++ : fail++
  console.log(`${cond ? '  PASS' : '  FAIL'}  ${name}${cond ? '' : `\n         ${detail}`}`)
}

console.log('\nB306 — the effect form\'s variable lists\n')

// ── The live case ─────────────────────────────────────────────
// `scopeVariables(trigger: "manual", sourceKind: "trait_setting")` answers with
// one entry, and `effectVariables` with the declared variable beside it.
const activation = [{ name: 'trait_setting', type: 'traitsetting' }]
const scope = {
  trait_setting: { element: 'traitsetting', cardinality: 'one' },
  order: { element: 'int', cardinality: 'one' },
  formation_rating: { element: 'rating_die', cardinality: 'many' },
}

const entries = scopeEntries(activation, scope)
ok('the activation name is in scope, typed as a catalog element',
   entries.trait_setting, { element: 'traitsetting', cardinality: 'one' })
ok('a declared variable keeps its element and cardinality',
   entries.formation_rating, { element: 'rating_die', cardinality: 'many' })
ok('every name the paths offer is in scope, in order',
   Object.keys(entries), ['trait_setting', 'order', 'formation_rating'])

// ── The die picker ────────────────────────────────────────────
const dice = dieVariablesFor(entries, false)
no('the die picker drops the source token (a trait instance is not a die)',
   !dice.includes('trait_setting'), `offered ${JSON.stringify(dice)}`)
no('the die picker drops a many-valued declared variable',
   !dice.includes('formation_rating'), `offered ${JSON.stringify(dice)}`)
no('the die picker drops a non-die scalar', !dice.includes('order'),
   `offered ${JSON.stringify(dice)}`)

// The positive case the fix exists for: a name that *is* a die, declared on the
// rule, now reaches the picker — it did not before, because it is not an
// activation name.
const withDie = scopeEntries(activation, {
  ...scope, effect_die_of_mine: { element: 'die', cardinality: 'one' },
})
ok('a declared single-valued die is offered', dieVariablesFor(withDie, false),
   ['effect_die_of_mine'])
ok('a die and the roll context, in that order',
   dieVariablesFor(withDie, true),
   ['effect_die_of_mine', 'effect_die', 'total', 'triggered_die_tier',
    'triggered_die_effect_die', 'triggered_die_result', 'triggered_die_die'])

// ── The chips ─────────────────────────────────────────────────
const chips = chipVariablesFor(entries, false)
ok('the chips list every name in scope, not only the activation\'s', chips, [
  { name: 'trait_setting', type: 'traitsetting' },
  { name: 'order', type: 'int' },
  { name: 'formation_rating', type: 'rating_die · many' },
])
no('a many-valued name is marked, not hidden',
   chips.some(c => c.name === 'formation_rating' && c.type.includes('many')),
   JSON.stringify(chips))
no('a roll-timed effect is given the roll context',
   chipVariablesFor(entries, true).some(c => c.name === 'effect_die'),
   JSON.stringify(chipVariablesFor(entries, true)))
no('a non-roll effect is not',
   !chipVariablesFor(entries, false).some(c => c.name === 'effect_die'),
   JSON.stringify(chipVariablesFor(entries, false)))

// ── The activation array alone still works (no typed scope yet) ──
// The panels fill in asynchronously; before `outputVariables` arrives the form
// has only the activation array, and it must not go blank.
ok('the activation array alone still lists its names',
   Object.keys(scopeEntries(activation, {})), ['trait_setting'])
no('a die-typed activation name is offered',
   dieVariablesFor(scopeEntries([{ name: 'some_die', type: 'die' }], {}), false)
     .includes('some_die'))

// ── The form is actually wired to it ──────────────────────────
const form = readFileSync(new URL('../src/components/gm/EffectForm.vue', import.meta.url), 'utf8')
no('EffectForm imports the rule', form.includes("from '@/composables/effectScopeVariables.js'"),
   'the import is gone — the screen no longer follows the checked rule')
no('the chips are built by it', /chipVariables\s*=\s*computed\(\(\)\s*=>\s*chipVariablesFor\(/.test(form),
   'chipVariables no longer calls chipVariablesFor()')
no('the die list is built by it', /dieVariables\s*=\s*computed\(\(\)\s*=>\s*dieVariablesFor\(/.test(form),
   'dieVariables no longer calls dieVariablesFor()')

console.log(`\n${pass} pass / ${fail} fail\n`)
process.exit(fail ? 1 : 0)
