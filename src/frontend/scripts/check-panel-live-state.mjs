/**
 * Executable check for the rule this bug broke: a panel reads **live session
 * state** from App's provide, never from a spec prop.
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-panel-live-state.mjs
 *
 * The report: *"I can assume it through the root GM panel… but not through a
 * floating panel that's been loaded through persistence"*, then, with the panel
 * open, *"props.entityId and props.currentEntityId [are both] character-20809…
 * I'm a roaming GM at the moment."*
 *
 * A spec prop is a **copy taken when a panel is opened** (`openEntityEdit` writes
 * `currentEntityId: props.entityId` into the child spec). A detached window keeps
 * the copy it was spawned with, and a restored one keeps the copy that was
 * written to `localStorage` — so any `v-if` that gates on one is answering a
 * question about the past. The perspective and the GM's location are live facts,
 * and App provides both (`actingEntityId`, `gmCurrentLocationId`); the props
 * survive only as the fallback for a panel mounted without that provide.
 */
import { readFileSync, readdirSync } from 'node:fs'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}
const yes = (name, got) => ok(name, !!got, true)

const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8')
const ENTITY_PANEL = read('../src/components/gm/GmEntityEditPanel.vue')
const GM_PANEL = read('../src/components/GmPanel.vue')
const APP = read('../src/App.vue')

// ── the two live facts App provides ─────────────────────────────────────
console.log('\nthe live values are provided, and used\n')

yes('the acting entity is provided live', /provide\('actingEntityId', computed\(\(\) => entityId\.value/.test(APP))
yes('and the GM\'s location', /provide\('gmCurrentLocationId', computed\(\(\) => currentLocationId\.value\)/.test(APP))
yes('the entity panel injects the first, with the prop only as a fallback',
  /const actingEntityId = inject\('actingEntityId', null\) \|\| computed\(\(\) => props\.currentEntityId/.test(ENTITY_PANEL))
yes('and the second the same way',
  /const gmLocationId = inject\('gmCurrentLocationId', null\) \|\| computed\(\(\) => props\.currentLocationId/.test(ENTITY_PANEL))

// ── the gate that broke ────────────────────────────────────────────────
console.log('\nthe Assume gate reads the live perspective\n')

const assumeGate = ENTITY_PANEL.match(/v-if="\(form\.type === 'CHARACTER' \|\| form\.type === 'GMC'\)[^"]*"/)
ok('the Assume button is still gated on "not already acting as this"', !!assumeGate, true)
yes('  …against the live injected value', /entityId !== actingEntityId/.test(assumeGate?.[0] || ''))
ok('  …and NOT against the frozen prop',
  /currentEntityId/.test(assumeGate?.[0] || ''), false)
yes('the sibling Import button reads its live value too',
  /canImportToLocation = computed\(\(\) =>[\s\S]{0,160}gmLocationId\.value/.test(ENTITY_PANEL))

// ── the class, not just the instance ───────────────────────────────────
// Any panel under `gm/` that gates rendering on one of the copied props is the
// same bug waiting: in a float it answers about whenever that panel was opened.
console.log('\nand no other panel gates on a copied prop\n')

const dir = new URL('../src/components/gm/', import.meta.url)
const offenders = []
for (const name of readdirSync(dir).filter((f) => f.endsWith('.vue'))) {
  const src = readFileSync(new URL(name, dir), 'utf8')
  const template = src.slice(0, src.indexOf('<script'))
  for (const line of template.split('\n')) {
    // `props.x` inside the script is deliberate (the fallbacks); the *template* is
    // where a stale value becomes a wrong button.
    if (/v-if|v-show/.test(line) && /currentEntityId|currentLocationId/.test(line)) {
      offenders.push(`${name}: ${line.trim()}`)
    }
  }
}
ok('no gm panel gates a v-if/v-show on currentEntityId/currentLocationId', offenders, [])

// ── the fallback path is still intact ──────────────────────────────────
// The props are not dead: a panel mounted without App's provide (a spec test, a
// future embedding) still resolves them.
yes('the spec still carries both props, so the fallback works',
  /props: \{ entityId: selectedId\.value, currentEntityId: props\.entityId, currentLocationId: props\.currentLocationId \}/.test(GM_PANEL))
yes('and the panel still declares them', /currentEntityId: \{ type: String, default: '' \}/.test(ENTITY_PANEL))

console.log(`\n${pass} passed, ${fail} failed\n`)
process.exit(fail ? 1 : 0)
