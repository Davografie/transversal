/**
 * Static contract check for the sheet's row/detail components and its emits.
 *
 * The build cannot see any of the failure modes below — they are runtime
 * TypeErrors, or a control that silently does nothing — so they are checked here:
 *
 *  1. **Scope.** These components receive their helpers through an `api` PROP.
 *     In the template a bare `api.x` is correct (props are exposed), but inside
 *     `<script setup>` it must be `props.api.x` — a bare `api` there is a
 *     ReferenceError at render. This shipped once; hence this check.
 *  2. **Membership.** Every `api.<member>` a component uses must exist on the
 *     object the sheet hands over (`traitRowApi` / `detailApi`), or the call is
 *     `undefined is not a function`.
 *  3. **Emit wiring.** Every emit the sheet declares must be handled by its host
 *     as `@kebab-case`, and every handler on the host must match a declared
 *     emit. A mismatch is a control that does nothing when clicked — no error,
 *     no warning, just a dead button.
 *
 * Run it against the frontend image:
 *
 *   docker run --rm -v /path/to/src/frontend:/work:ro -w /work \
 *     transversal2-frontend:latest node scripts/check-sheet-api.mjs
 */

import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

const SHEET_DIR = 'src/components/sheet'
const SHEET = 'src/components/CharacterSheet.vue'
const HOST = 'src/App.vue'

const sheetSrc = readFileSync(SHEET, 'utf8')

/** Pull the members the sheet hands to a component, from `const <name> = { ... }`. */
function providedMembers(objectName) {
  const m = sheetSrc.match(new RegExp(`const ${objectName} = \\{(.*?)\\n\\}`, 's'))
  if (!m) throw new Error(`could not find ${objectName} in ${SHEET}`)
  return new Set(m[1].match(/[A-Za-z_$][\w$]*/g) || [])
}

function sections(src) {
  const script = (src.match(/<script setup>([\s\S]*?)<\/script>/) || [, ''])[1]
  const template = (src.match(/<template>([\s\S]*?)<\/template>/) || [, ''])[1]
  return { script, template }
}

/**
 * Drop comments, keeping line numbering. A comment that *documents* `api.x` is
 * not a bare reference — and the first version of this check flagged exactly
 * that, which is a false alarm loud enough to train people to ignore it.
 */
function withoutComments(code) {
  return code
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '))
    .replace(/\/\/[^\n]*/g, '')
}

const members = {
  traitRowApi: providedMembers('traitRowApi'),
  detailApi: providedMembers('detailApi'),
}

// Which api object each component is wired to (from its prop type in the parent).
function apiObjectFor(file) {
  // TraitDetailPanel and TraitRow both take `api`; the sheet passes the
  // matching object. Keep this map explicit so a new component must declare.
  const map = { 'TraitRow.vue': 'traitRowApi', 'TraitDetailPanel.vue': 'detailApi' }
  return map[file] || null
}

let fail = 0
const report = (ok, msg) => { if (!ok) fail++; console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${msg}`) }

const files = readdirSync(SHEET_DIR).filter((f) => f.endsWith('.vue'))
console.log('\nsheet component ↔ api contract\n')

for (const file of files) {
  const objectName = apiObjectFor(file)
  if (!objectName) continue
  const src = readFileSync(join(SHEET_DIR, file), 'utf8')
  const { script, template } = sections(src)

  // 1. scope: no bare `api.` in <script setup> — it must be `props.api.`
  const scan = withoutComments(script)
  const bareInScript = [...scan.matchAll(/(^|[^.\w$])api\./g)]
    .filter((m) => !/props\.$/.test(m[1]))
    .map((m) => scan.slice(0, m.index).split('\n').length)
  report(bareInScript.length === 0,
    `${file}: no bare \`api.\` in <script setup>` +
    (bareInScript.length ? ` — found at script line(s) ${bareInScript.join(', ')}; use \`props.api\`` : ''))

  // 2. membership: every api.<member> used anywhere must exist
  const used = new Set([...script.matchAll(/\bapi\.([A-Za-z_$][\w$]*)/g)].map((m) => m[1]))
  for (const m of template.matchAll(/\bapi\.([A-Za-z_$][\w$]*)/g)) used.add(m[1])
  const missing = [...used].filter((n) => !members[objectName].has(n))
  report(missing.length === 0,
    `${file}: every api member exists on ${objectName} (${used.size} used)` +
    (missing.length ? ` — missing: ${missing.join(', ')}` : ''))
}

// ── 3. emit wiring: the sheet's emits ↔ the host's handlers ──────────────
// Vue turns an unhandled emit into a no-op, so a renamed emit or a mistyped
// handler is invisible until someone clicks the control and nothing happens.
const kebab = (s) => s.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase()

const declaredEmits = (() => {
  const m = sheetSrc.match(/defineEmits\(\[([^\]]*)\]\)/)
  if (!m) throw new Error(`could not find defineEmits in ${SHEET}`)
  return m[1].match(/'([^']+)'/g)?.map((s) => s.slice(1, -1)) || []
})()

const hostHandlers = (() => {
  const hostSrc = readFileSync(HOST, 'utf8')
  // The component's own tag: from `<CharacterSheet` to its self-closing `/>`.
  const m = hostSrc.match(/<CharacterSheet\b([\s\S]*?)\/>/)
  if (!m) throw new Error(`could not find a <CharacterSheet … /> tag in ${HOST}`)
  return [...m[1].matchAll(/@([a-z][\w-]*)=/g)].map((x) => x[1])
})()

const wanted = declaredEmits.map(kebab)
const missingHandlers = wanted.filter((w) => !hostHandlers.includes(w))
const orphanHandlers = hostHandlers.filter((h) => !wanted.includes(h))

report(missingHandlers.length === 0,
  `every declared emit is handled in ${HOST} (${declaredEmits.length} emits)` +
  (missingHandlers.length ? ` — no handler for @${missingHandlers.join(', @')}` : ''))
report(orphanHandlers.length === 0,
  `every ${HOST} handler matches a declared emit` +
  (orphanHandlers.length ? ` — @${orphanHandlers.join(', @')} is dead (no such emit)` : ''))

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
