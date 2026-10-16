/**
 * Executable check for SFX duplication ([[B298]]).
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image, the same
 * way as the other checks:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-sfx-duplicate.mjs
 *
 * The request: *"I'd like to be able to duplicate SFX's. It'll make authoring
 * similar SFX's easier."*
 *
 * Three things here that a green build cannot see:
 *
 * 1. **The condition mapping runs.** A panel's emit name and the opener's
 *    listener key are two strings that must match, and `v-on` with no matching
 *    emit is a silent no-op — the duplicate panel would open, do its work, and
 *    nothing would follow. So the child's `defineEmits` is read and compared with
 *    the keys the opener listens for.
 * 2. **`initialConditions` is executed**, not restated: it is lifted out of the
 *    composable and run, because the `targets` field it had forgotten is a
 *    latent erasure (a value the form cannot see is a value it discards —
 *    [[B273]]'s class) and nothing live would notice it going missing again.
 * 3. **The copy opens with no owner.** The author's decision is that a duplicate
 *    is always unattached, so the editor must not be told it "Lives on" whatever
 *    the management screen happens to be filtered by.
 */
import { readFileSync } from 'node:fs'

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

const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8')
const MGMT = read('../src/components/gm/GmSfxManagementPanel.vue')
const DUPLICATE = read('../src/components/gm/GmSfxDuplicatePanel.vue')
const USE_SFX_EDIT = read('../src/composables/useSfxEdit.js')

/** The shipped text between two markers, so it can be run as written. */
function between(src, from, to) {
  const i = src.indexOf(from)
  if (i < 0) throw new Error(`not found: ${from}`)
  const j = src.indexOf(to, i)
  if (j < 0) throw new Error(`not found: ${to}`)
  return src.slice(i, j)
}

// ── 1. The panel's emit and the opener's listener agree ────────────────────
const emitted = [...DUPLICATE.matchAll(/defineEmits\(\[([^\]]*)\]\)/g)]
  .flatMap((m) => [...m[1].matchAll(/'([^']+)'/g)].map((x) => x[1]))
ok('the duplicate panel declares exactly one emit', emitted, ['duplicated'])

const listenerBlock = between(
  MGMT.slice(MGMT.indexOf('component: GmSfxDuplicatePanel')),
  'listeners: {', '}')
const listened = [...listenerBlock.split('\n').slice(1).join('\n')
  .matchAll(/^\s*([a-z-]+):/gm)].map((m) => m[1])
ok('the opener hears it', listened, emitted)

// ── 2. The panel is opened, and the copy is opened on nobody ──────────────
no('the management panel imports the duplicate panel',
   /import GmSfxDuplicatePanel from '\.\/GmSfxDuplicatePanel\.vue'/.test(MGMT))
no('a row offers the duplicate affordance',
   /@click\.stop="duplicateSfx\(s\)"/.test(MGMT))
no('the copy is opened with an explicit null owner, not the active filter',
   /openSfx\(created,\s*null\)/.test(MGMT))
no('openSfx only falls back to the owner filter when no owner was passed',
   /owner === undefined \? ownerRef\.value : owner/.test(MGMT),
   'without the sentinel an explicit `null` owner would be replaced by the filter')

// ── 3. `initialConditions` runs, and keeps a multi-valued condition ────────
const fnText = between(USE_SFX_EDIT, 'function initialConditions(sfx) {', '\n}')
const initialConditions = new Function(`return (${fnText}\n})`)()

const multi = initialConditions({
  conditions: [{ type: 'PHASE', subject: '', target: '', targets: ['picking', 'giving_in'],
                 value: '', operator: '>=', narrative: '', spec: { steps: [] } }],
})
ok('a multi-valued condition keeps every value', multi[0].targets, ['picking', 'giving_in'])
ok('…and keeps its singular `target` as stored', multi[0].target, '')

const single = initialConditions({ conditions: [{ type: 'PHASE', target: 'picking', targets: ['picking'] }] })
ok('a single-valued condition is unchanged', [single[0].target, single[0].targets], ['picking', ['picking']])

const legacy = initialConditions({ limit: 'Once per scene' })
ok('the legacy `limit` still becomes a narrative condition',
   [legacy[0].type, legacy[0].narrative], ['NARRATIVE', 'Once per scene'])

const none = initialConditions(null)
ok('no rule is no conditions', none, [])

// ── 4. The mutation carries the fields a copy must not lose ───────────────
// The copy itself is made server-side from the *stored* rule, but the object the
// editor is handed must carry the rule whole or it renders an empty one.
for (const field of ['refs', 'targetSpec', 'entitySpec', 'ownerSpec', 'resultSpec',
                     'boundVariables', 'listenerSpec', 'reach', 'dieFilter', 'duration']) {
  no(`the mutation returns \`${field}\``, DUPLICATE.includes(field))
}

console.log(`\n  ${fail ? `${fail} failed, ` : ''}${pass} passed`)
process.exit(fail ? 1 : 0)
