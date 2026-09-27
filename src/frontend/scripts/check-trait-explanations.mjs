/**
 * Executable check for seeing and editing a trait's and a traitset's explanation.
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image, the same
 * way as the other checks:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-trait-explanations.mjs
 *
 * The request: "I'd like to be able to see and edit traitset and trait
 * explanations."
 *
 * Both fields have existed on the domain model all along and the migrations
 * populated them — **119 live traits** carry an `explanation`, and the traitset
 * side migrated in as `description` (the old app's `explainer`) before being
 * renamed to `explanation` under B227. Nothing surfaced either, and neither
 * editor had a field, so the text was invisible and uneditable.
 *
 * The backend half landed under **B227** ([[backend-platform]]): the field on
 * both refs, the write inputs, the converters, the four `TraitRef` construction
 * sites, and `tests/test_registry_explanation.py`. B227's own *Needs another role*
 * hands this session the authoring field — "one textarea each" — which is what
 * this check covers.
 */
import { readFileSync } from 'node:fs'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}

const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8')
const CONFIG = read('../src/composables/useTraitsConfig.js')
const TRAIT = read('../src/components/gm/GmTraitEditPanel.vue')
const SET = read('../src/components/gm/GmTraitsetDetail.vue')
const CSS = read('../src/assets/gm-panel.css')

// ── 1. the reads carry the fields ───────────────────────────────────────
console.log('\nthe traits config selects both fields\n')

ok('the traitsets query selects `explanation`',
  /traitsets \{[\s\S]*?sheetTab explanation/.test(CONFIG), true)
ok('the traits query selects `explanation`',
  /traits \{[\s\S]*?polarity tags explanation/.test(CONFIG), true)

// ── 2. the trait editor ─────────────────────────────────────────────────
console.log('\nGmTraitEditPanel — explanation is loaded, edited and saved\n')

ok('the edit form has the field', /v-model="form\.explanation"/.test(TRAIT), true)
ok('the create form has it too', /v-model="createForm\.explanation"/.test(TRAIT), true)
ok('the form state carries it', /explanation: '',/.test(TRAIT), true)
ok('opening a trait loads it', /form\.explanation = t\.explanation \|\| ''/.test(TRAIT), true)
// The debounced auto-save follows an explicit field list: a field missing here
// never saves at all, which reads as "the editor is broken".
ok('the auto-save watches it', /\(\) => form\.explanation,/.test(TRAIT), true)
ok('the update mutation sends it',
  /input: \{[^}]*explanation: form\.explanation/.test(TRAIT), true)
ok('the local echo patches it, so the reopened panel shows the new text',
  /patchData\('traits'[\s\S]{0,400}?explanation: form\.explanation/.test(TRAIT), true)
ok('the create mutation sends it',
  /explanation: createForm\.explanation/.test(TRAIT), true)

// ── 3. the traitset editor ──────────────────────────────────────────────
console.log('\nGmTraitsetDetail — the explanation is loaded, edited and saved\n')

ok('the form has the field', /v-model="form\.explanation"/.test(SET), true)
ok('the form state carries it', /sheetTab: 'TRAITS', explanation: ''/.test(SET), true)
ok('opening a set loads it', /form\.explanation = ts\.explanation \|\| ''/.test(SET), true)
ok('the auto-save watches it', /\(\) => form\.explanation\]/.test(SET), true)
ok('the mutation declares the variable', /\$explanation: String/.test(SET), true)
ok('the mutation passes it through', /explanation: \$explanation/.test(SET), true)
ok('the variables bind it to the form', /sheetTab: form\.sheetTab, explanation: form\.explanation/.test(SET), true)
ok('the local echo patches it',
  /patchData\('traitsets'[\s\S]{0,400}?explanation: form\.explanation/.test(SET), true)

// ── 4. the field is styled ──────────────────────────────────────────────
console.log('\nthe field renders as a box, not bare text\n')

// `input, select` get the box from the global stylesheet; `textarea` is not in
// that rule, so without this a panel textarea renders as unstyled text.
ok('a panel textarea gets the input box', /\.ps-form textarea \{/.test(CSS), true)
ok('and the same focus treatment', /\.ps-form textarea:focus/.test(CSS), true)

// ── 5. the pre-fix shape, which must lose the text ──────────────────────
console.log('\nthe pre-fix payload, which drops the field\n')

// The mutation input is an explicit object literal, so a field absent from it is
// a field the write silently discards.
const preFixTraitInput = `{ id: trait.value.id, input: { name: form.name, defaultDieType: form.defaultDieType, tags: form.tags, polarity: form.polarity || null } }`
const shippedTraitInput = (TRAIT.match(/input: \{[^}]*\}/) || [''])[0]
// The traitset mutation took only the fields it named, so a variable it never
// declared could not be sent at all.
const preFixSetMutation = `mutation($id: ID!, $name: String, $sheetTab: SheetTab) { updateTraitset(id: $id, name: $name, sheetTab: $sheetTab) { id } }`

ok('pre-fix: the trait update input had no explanation to send',
  /explanation:/.test(preFixTraitInput), false)
ok('shipped: the same input does',
  /explanation: form\.explanation/.test(shippedTraitInput), true)
ok('pre-fix: the traitset mutation had no variable for it',
  /\$explanation/.test(preFixSetMutation), false)
ok('shipped: it declares and passes one',
  /\$explanation: String/.test(read('../src/components/gm/GmTraitsetDetail.vue')), true)

console.log(`\n${pass} passed, ${fail} failed\n`)
process.exit(fail ? 1 : 0)
