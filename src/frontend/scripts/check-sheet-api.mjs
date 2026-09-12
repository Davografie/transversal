/**
 * Static contract check for the sheet's row/detail components.
 *
 * The build cannot see either of the two failure modes below — both are runtime
 * TypeErrors in the browser — so they are checked here:
 *
 *  1. **Scope.** These components receive their helpers through an `api` PROP.
 *     In the template a bare `api.x` is correct (props are exposed), but inside
 *     `<script setup>` it must be `props.api.x` — a bare `api` there is a
 *     ReferenceError at render. This shipped once; hence this check.
 *  2. **Membership.** Every `api.<member>` a component uses must exist on the
 *     object the sheet hands over (`traitRowApi` / `detailApi`), or the call is
 *     `undefined is not a function`.
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
  const bareInScript = [...script.matchAll(/(^|[^.\w$])api\./g)]
    .filter((m) => !/props\.$/.test(m[1]))
    .map((m) => script.slice(0, m.index).split('\n').length)
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

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
