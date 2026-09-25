/**
 * Executable check for the create-entity panel's type-driven fields (P5.7).
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-entity-create.mjs
 *
 * What was wrong: `GmEntityCreatePanel.vue` rendered razmerit for **every**
 * type while `GmEntityForm.vue` (the edit panel) hid it unless the type was
 * rated — so the same entity was authored differently depending on which door
 * you came through. The rule now lives once, in `constants/entityTypes.js`, and
 * both panels ask it.
 *
 * The structural half of this check reads the two shipping `.vue` files as
 * text. That is deliberate: the bug was not a wrong value, it was a *second*
 * copy of the rule, and only the source can show whether a second copy is back.
 * The predicate is asserted against a pre-fix snippet too, so it cannot pass by
 * matching nothing.
 */
import { readFileSync } from 'node:fs'

import { hasRazmerit, ENTITY_TYPES } from '../src/constants/entityTypes.js'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}

const CREATE = readFileSync(new URL('../src/components/gm/GmEntityCreatePanel.vue', import.meta.url), 'utf8')
const EDIT = readFileSync(new URL('../src/components/gm/GmEntityForm.vue', import.meta.url), 'utf8')
const TYPES = readFileSync(new URL('../src/constants/entityTypes.js', import.meta.url), 'utf8')

// ── 1. the rule ──────────────────────────────────────────────────────────
console.log('\nrazmerit — which types are rated\n')

ok('CHARACTER is rated', hasRazmerit('CHARACTER'), true)
ok('GMC is rated', hasRazmerit('GMC'), true)
ok('FACTION is rated', hasRazmerit('FACTION'), true)
ok('LOCATION is not — it is a place', hasRazmerit('LOCATION'), false)
ok('UNIVERSE is not — it is a container', hasRazmerit('UNIVERSE'), false)
ok('ASSET is not', hasRazmerit('ASSET'), false)
ok('an absent type is not rated', [hasRazmerit(''), hasRazmerit(undefined), hasRazmerit(null)], [false, false, false])
ok('the GraphQL enum casings the payload may use both answer alike',
  [hasRazmerit('location'), hasRazmerit('gmc')], [false, true])

// Every type the create panel can offer must have an answer, so a type added
// later cannot fall through the visibility rule unnoticed.
ok('every offerable type answers the question',
  ENTITY_TYPES.map((t) => [t, hasRazmerit(t)]),
  [['CHARACTER', true], ['GMC', true], ['ASSET', false], ['FACTION', true], ['UNIVERSE', false], ['LOCATION', false]])

// ── 2. one copy of the rule ──────────────────────────────────────────────
console.log('\none copy of the rule — the drift that caused the bug\n')

ok('the constant is defined in the shared module', /export const RAZMERIT_TYPES = new Set\(/.test(TYPES), true)
ok('the edit panel imports the shared rule', /import \{[^}]*hasRazmerit[^}]*\} from '@\/constants\/entityTypes\.js'/.test(EDIT), true)
ok('the create panel imports the shared rule', /import \{[^}]*hasRazmerit[^}]*\} from '@\/constants\/entityTypes\.js'/.test(CREATE), true)
ok('neither panel keeps its own copy of the type list',
  [CREATE.includes("new Set(['CHARACTER'"), EDIT.includes("new Set(['CHARACTER'")], [false, false])

// ── 3. the field is actually guarded ─────────────────────────────────────
console.log('\nthe create panel hides what it does not rate\n')

// The razmerit control is the `.raz-dots` radiogroup; the field only counts as
// hidden when that group sits inside a `v-if="showRazmerit"` block.
function razmeritGuarded(src) {
  const i = src.indexOf('class="raz-dots"')
  if (i < 0) return false
  const open = src.lastIndexOf('<template', i)
  if (open < 0) return false
  return /v-if="showRazmerit"/.test(src.slice(open, i))
}

ok('the razmerit control is wrapped in a `showRazmerit` guard', razmeritGuarded(CREATE), true)
ok('and its label is inside that guard too',
  CREATE.slice(CREATE.lastIndexOf('<template', CREATE.indexOf('class="raz-dots"')), CREATE.indexOf('class="raz-dots"')).includes('Razmerit'), true)

// The predicate must be able to fail: the shipped pre-fix markup — an unguarded
// group — has to come back false, or a check that matches nothing would read as
// a pass.
ok('the guard predicate rejects the pre-fix unguarded markup',
  razmeritGuarded('<label>Razmerit</label>\n<div class="raz-dots" role="radiogroup"></div>'), false)

ok('the create panel derives visibility from the shared rule',
  /const showRazmerit = computed\(\(\) => hasRazmerit\(form\.type\)\)/.test(CREATE), true)
ok('the edit panel derives it from the same rule',
  /const showRazmerit = computed\(\(\) => hasRazmerit\(local\.value\.type\)\)/.test(EDIT), true)

// ── 4. the reset, executed ───────────────────────────────────────────────
console.log('\nchanging type on the create panel\n')

// The shipped watcher body, lifted out of the SFC and run — so the reset is
// tested as written rather than re-implemented here.
const watcher = CREATE.match(/watch\(\(\) => form\.type, \(t\) => \{([\s\S]*?)\n\}\)/)
if (!watcher) { ok('the type watcher was found', false, true) }
else {
  const body = watcher[1]
  const run = new Function('form', 't', 'hasRazmerit', body)
  const typed = () => ({ name: '', type: 'CHARACTER', location: 'loc-craigmuir', razmerit: 3 })

  const toLocation = typed(); run(toLocation, 'LOCATION', hasRazmerit)
  ok('switching to LOCATION clears the razmerit already clicked', toLocation.razmerit, 0)
  ok('and leaves the location alone', toLocation.location, 'loc-craigmuir')

  const toUniverse = typed(); run(toUniverse, 'UNIVERSE', hasRazmerit)
  ok('switching to UNIVERSE clears both', [toUniverse.razmerit, toUniverse.location], [0, ''])

  const toGmc = typed(); run(toGmc, 'GMC', hasRazmerit)
  ok('switching to a rated type keeps the razmerit', [toGmc.razmerit, toGmc.location], [3, 'loc-craigmuir'])

  const toAsset = typed(); run(toAsset, 'ASSET', hasRazmerit)
  ok('switching to ASSET clears it — assets are not rated', toAsset.razmerit, 0)
}

// ── 5. what the panel offers (the other two P5.7 clauses) ────────────────
console.log('\nthe create panel offers the types it must\n')

ok('UNIVERSE is offerable — its type list is the shared one', /v-for="t in ENTITY_TYPES"/.test(CREATE), true)
ok('a universe cannot be given a location', /:disabled="form\.type === 'UNIVERSE'"/.test(CREATE), true)
ok('an add row prefills the type it trails',
  /const typeByAdd = \{ occupant: 'CHARACTER', location: 'LOCATION', universe: 'UNIVERSE' \}/.test(
    readFileSync(new URL('../src/components/GmPanel.vue', import.meta.url), 'utf8')), true)
ok('an occupant add row is given its location as the parent',
  readFileSync(new URL('../src/components/GmPanel.vue', import.meta.url), 'utf8')
    .includes("ctx?.addType === 'occupant' ? ctx.parentId : ''"), true)

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
