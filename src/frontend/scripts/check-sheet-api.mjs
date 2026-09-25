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
const EDITOR = 'src/composables/useTraitEditor.js'

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

// ── 4. a prevented context menu must do something ────────────────────────
// `@contextmenu.prevent` with no handler swallows the right-click and opens
// nothing — the row simply stops responding, which is how "RMB on a sub-trait
// does nothing" reached the human. Every occurrence must carry a handler.
{
  const rowSrc = readFileSync(join(SHEET_DIR, 'TraitRow.vue'), 'utf8')
  const bare = [...rowSrc.matchAll(/@contextmenu\.prevent(?!\s*=)/g)]
    .map((m) => rowSrc.slice(0, m.index).split('\n').length)
  report(bare.length === 0,
    'TraitRow.vue: no `@contextmenu.prevent` without a handler' +
    (bare.length ? ` — bare at line(s) ${bare.join(', ')}; right-click would do nothing` : ''))
  const withEdit = (rowSrc.match(/@contextmenu\.prevent="api\.startEdit\(trait\)"/g) || []).length
  report(withEdit >= 2,
    `TraitRow.vue: both the top-level and the nested row open the editor on right-click (${withEdit} found)`)
}

// ── 5. the editor must resolve a NESTED setting ──────────────────────────
// `editingTrait` resolves its id out of the lists the sheet renders. A
// sub-trait's setting is nested under its parent, so a top-level scan returns
// null and the editor never opens — the handler fires and nothing happens.
// Ids are looked up with `findSetting` (recursive) for exactly this reason.
{
  const editorSrc = readFileSync(EDITOR, 'utf8')
  const topLevelOnly = [...editorSrc.matchAll(/\.traits\.find\(|traits\.value\.find\(/g)]
    .map((m) => editorSrc.slice(0, m.index).split('\n').length)
  report(topLevelOnly.length === 0,
    'useTraitEditor.js: no top-level-only trait lookups' +
    (topLevelOnly.length ? ` — line(s) ${topLevelOnly.join(', ')}; a nested id would resolve to null` : ''))
  report(/findSetting\(/.test(editorSrc),
    'useTraitEditor.js: resolves trait ids with the recursive findSetting')
}

// ── 6. one predicate for "is this a container?" (B142) ───────────────────
// Container-ness is a tag, and a tag test is the kind of thing a surface
// reinvents: the sheet, a picker and the GM panel would each spell
// `…tags.includes('container')` and drift. The test needs the union of registry
// and instance tags (B116), so a copy that forgets one half silently stops
// matching — which is exactly how "a container nested inside a container was
// unreachable" happened. The predicate is `isContainer` in `utils/traitTree.js`
// (over `traitTags`); a bare tag comparison anywhere else is what a copy looks
// like. The check is on the *comparison*, not the bare word, so a class name
// such as `pool-dice-container` is not a hit.
{
  const OWNER = 'src/utils/traitTree.js'
  const TAG_COMPARISON = /(?:includes\(\s*|===?\s*|!==?\s*)(['"])container\1|(['"])container\2\s*(?:===?|!==?)/g
  const offenders = []
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name)
      if (entry.isDirectory()) { walk(path); continue }
      if (!/\.(js|mjs|vue)$/.test(entry.name)) continue
      if (path.replace(/\\/g, '/') === OWNER) continue
      const src = withoutComments(readFileSync(path, 'utf8'))
      for (const m of src.matchAll(TAG_COMPARISON)) {
        offenders.push(`${path}:${src.slice(0, m.index).split('\n').length}`)
      }
    }
  }
  walk('src')
  report(offenders.length === 0,
    `"is this a container?" is asked only in ${OWNER}` +
    (offenders.length ? ` — a second tag test at ${offenders.join(', ')}; use isContainer (its tags are registry ∪ instance)` : ''))
  const ownerSrc = readFileSync(OWNER, 'utf8')
  report(/export function isContainer\(trait\)\s*\{[\s\S]*?traitTags\(/.test(ownerSrc),
    `${OWNER}: isContainer resolves tags through traitTags (registry ∪ instance)`)
}

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
