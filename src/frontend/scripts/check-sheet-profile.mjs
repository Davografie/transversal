/**
 * Executable check for the per-entity-type sheet profiles.
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend:/work:ro \
 *     -w /work transversal2-frontend:latest node scripts/check-sheet-profile.mjs
 *
 * It pins the two things that are easy to get wrong and expensive to notice:
 * that the occupant sheet is **unchanged** (every entity that is not a location
 * or a faction must still behave exactly as before), and that no profile can
 * drop the trait machinery, which every sheet needs.
 */

import {
  DEFAULT_SHEET_TAB,
  OCCUPANT_TYPES,
  SHEET_TABS,
  hasSheetTab,
  isOccupantType,
  sheetProfileFor,
} from '../src/utils/sheetProfile.js'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}

console.log('\nsheet profiles — per entity type\n')

// ── occupants are the sheet as it was ────────────────────────────────────
for (const t of OCCUPANT_TYPES) {
  const p = sheetProfileFor(t)
  ok(`${t} → occupant`, p.kind, 'occupant')
  ok(`${t} keeps razmerit`, p.razmerit, true)
  ok(`${t} keeps all four original tabs`,
     [...p.tabs], ['profile', 'traits', 'bluebook', 'lifepath'])
}

// ── a location is a place ────────────────────────────────────────────────
const loc = sheetProfileFor('LOCATION')
ok('LOCATION → location', loc.kind, 'location')
ok('a location has no razmerit', loc.razmerit, false)
ok('a location keeps its traits', hasSheetTab(loc, 'traits'), true)
ok('a location keeps its blue book', hasSheetTab(loc, 'bluebook'), true)
ok('a location shows incoming ties', hasSheetTab(loc, 'ties'), true)
ok('a location has no life paths (they are faction-bound)', hasSheetTab(loc, 'lifepath'), false)
ok('a location has no roster', hasSheetTab(loc, 'roster'), false)

// ── a faction is an organisation ─────────────────────────────────────────
const fac = sheetProfileFor('FACTION')
ok('FACTION → faction', fac.kind, 'faction')
ok('a faction keeps razmerit', fac.razmerit, true)
ok('a faction has a roster', hasSheetTab(fac, 'roster'), true)
ok('a faction has no life-path tab of its own', hasSheetTab(fac, 'lifepath'), false)
ok('a faction keeps its traits', hasSheetTab(fac, 'traits'), true)
// The roster *is* a faction's incoming ties, specialised — a general ties tab
// beside it would be the same edges read twice.
ok('a faction has no separate ties tab', hasSheetTab(fac, 'ties'), false)
ok('an occupant has no ties tab', hasSheetTab(sheetProfileFor('CHARACTER'), 'ties'), false)

// ── the same enum arrives in two spellings ───────────────────────────────
ok('lowercase location matches uppercase', sheetProfileFor('location'), loc)
ok('mixed case matches too', sheetProfileFor('LoCaTiOn'), loc)
ok('whitespace does not change the answer', sheetProfileFor(' location '), loc)

// ── everything not designed here stays on the occupant sheet ─────────────
for (const t of ['UNIVERSE', 'SUBTRAIT', 'RELATION', 'universe', '']) {
  ok(`unknown type ${JSON.stringify(t)} → occupant`, sheetProfileFor(t).kind, 'occupant')
}
ok('a null type (entity not loaded yet) → occupant', sheetProfileFor(null).kind, 'occupant')
ok('an undefined type → occupant', sheetProfileFor(undefined).kind, 'occupant')
ok('a number is tolerated', sheetProfileFor(7).kind, 'occupant')

// ── invariants every profile must hold ───────────────────────────────────
const every = [loc, fac, sheetProfileFor('CHARACTER')]
ok('every profile can show traits', every.every(p => hasSheetTab(p, 'traits')), true)
ok('no profile is tabless', every.every(p => p.tabs.length > 0), true)
ok('the fallback tab is one every profile has', every.every(p => hasSheetTab(p, DEFAULT_SHEET_TAB)), true)
ok('tabs never repeat', every.every(p => new Set(p.tabs).size === p.tabs.length), true)
ok('tab names come from the declared set',
   every.every(p => p.tabs.every(t => Object.values(SHEET_TABS).includes(t))), true)

// ── identity is stable, so a computed can compare cheaply ────────────────
ok('repeated lookups return the same object', sheetProfileFor('LOCATION') === sheetProfileFor('location'), true)
ok('occupant types share one profile', sheetProfileFor('CHARACTER') === sheetProfileFor('ASSET'), true)
ok('a profile cannot be mutated by a caller', (() => {
  try { sheetProfileFor('LOCATION').razmerit = true } catch { return true }
  return sheetProfileFor('LOCATION').razmerit === false
})(), true)

// ── isOccupantType agrees with the profiles ──────────────────────────────
ok('occupant types report true', OCCUPANT_TYPES.every(isOccupantType), true)
ok('non-occupants report false', ['LOCATION', 'FACTION', 'UNIVERSE', null].every(t => !isOccupantType(t)), true)
ok('hasSheetTab tolerates a missing profile', hasSheetTab(null, 'traits'), false)

console.log(`\n  ${pass} passed, ${fail} failed\n`)
process.exit(fail ? 1 : 0)
