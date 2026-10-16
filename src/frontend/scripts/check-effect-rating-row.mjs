/**
 * Executable check for the rating row a trait-creating effect authors ([[B307]]).
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image, the same
 * way as the other checks:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-effect-rating-row.mjs
 *
 * What a green build cannot see:
 *
 * 1. **That a stored row survives a round trip.** The form reads `context.dice`,
 *    and a value it does not read is a value it writes back empty — a gain at no
 *    rating, which looks like a gain that worked.
 * 2. **That old content is not erased.** Every effect authored before the row
 *    existed carries only a single `result`; the row is seeded from it, and the
 *    pair (`result` = the row's first die, `dice` = the row) is written together.
 * 3. **That a named die is still a named die.** Five live rules gain at
 *    `{effect_die}`; treating that as a literal row entry would put the token in a
 *    dice picker and lose the substitution.
 * 4. **That the form still uses it.** The rule lives in a composable so it can be
 *    run here; an un-wired import would leave the rule green and the screen wrong.
 */
import { readFileSync } from 'node:fs'
import { ratingFieldsFor, ratingRowFor } from '../src/composables/effectRatingRow.js'

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

console.log('\nB307 — the rating row\n')

// ── Loading ───────────────────────────────────────────────────
ok('a stored row is read back whole',
   ratingRowFor(['d6', 'd6', 'd6'], 'd6'), ['d6', 'd6', 'd6'])
ok('old content seeds the row from its single result',
   ratingRowFor(undefined, 'd8'), ['d8'])
ok('a stored row wins over the result it came from',
   ratingRowFor(['d10', 'd10'], 'd6'), ['d10', 'd10'])
ok('a named die is not a row',
   ratingRowFor(undefined, '{effect_die}'), [])
ok('nothing stays nothing',
   ratingRowFor(undefined, null), [])
ok('an empty stored row falls back to the result',
   ratingRowFor([], 'd6'), ['d6'])

// ── Saving ────────────────────────────────────────────────────
ok('the row is stored with its first die as `result`',
   ratingFieldsFor('die', ['d6', 'd6', 'd6'], ''), { result: 'd6', dice: ['d6', 'd6', 'd6'] })
ok('a one-die rating stores one die',
   ratingFieldsFor('die', ['d8'], ''), { result: 'd8', dice: ['d8'] })
ok('an emptied row is dropped, not written as []',
   ratingFieldsFor('die', [], ''), { result: '', dice: null })
ok('a named die is left exactly as typed',
   ratingFieldsFor('variable', [], '{effect_die}'), { result: '{effect_die}', dice: null })
ok('a path keeps `result` as the placeholder it was',
   ratingFieldsFor('spec', [], 'd4'), { result: 'd4', dice: null })
ok('blank entries in a row are not dice',
   ratingFieldsFor('die', ['d6', '', 'd8'], ''), { result: 'd6', dice: ['d6', 'd8'] })

// ── The round trip ────────────────────────────────────────────
const stored = ratingFieldsFor('die', ratingRowFor(undefined, 'd10'), 'd10')
ok('load then save is stable', stored, { result: 'd10', dice: ['d10'] })
ok('and stable again', ratingFieldsFor('die', ratingRowFor(stored.dice, stored.result), stored.result),
   { result: 'd10', dice: ['d10'] })

// ── The form is actually wired to it ──────────────────────────
const form = readFileSync(new URL('../src/components/gm/EffectForm.vue', import.meta.url), 'utf8')
no('EffectForm imports the rule', form.includes("from '@/composables/effectRatingRow.js'"),
   'the import is gone — the screen no longer follows the checked rule')
no('the row is read through it', /resultDice\s*=\s*computed\(\(\)\s*=>\s*ratingRowFor\(/.test(form),
   'resultDice no longer calls ratingRowFor()')
no('the payload is built through it', /ratingFieldsFor\(resultMode\.value/.test(form),
   'buildEffect no longer calls ratingFieldsFor()')
no('the load seeds the row through it', /knownCtx\.dice\s*=\s*ratingRowFor\(/.test(form),
   'populate no longer seeds the row from a legacy result')

// ── Only an action that declares the row gets one ─────────────
// `Add Die`, `Set Die`, `Play as Rating` and `Set Trait` take a single die, and
// their handlers ignore `context.dice` — a row there would collect dice that are
// silently dropped.
no('the row is gated on the action declaring it',
   /ratingIsRow\s*=\s*computed\([\s\S]{0,200}f\.name === 'dice'/.test(form),
   'ratingIsRow no longer reads the declared context field')
no('the row picker is gated', /resultMode === 'die' && ratingIsRow/.test(form),
   'the dice row renders unconditionally — a single-die action would get one')
no('the payload is gated too',
   /ratingIsRow\.value\s*\?\s*ratingFieldsFor\(/.test(form),
   'buildEffect writes context.dice for every action')
no('the load is gated', /if \(ratingIsRow\.value\) knownCtx\.dice/.test(form),
   'populate seeds context.dice for every action')
no('a single-die action still gets its dropdown',
   /v-else-if="resultMode === 'die'"[\s\S]{0,200}item\.f\.options/.test(form),
   'the plain die dropdown is gone')

console.log(`\n${pass} pass / ${fail} fail\n`)
process.exit(fail ? 1 : 0)
