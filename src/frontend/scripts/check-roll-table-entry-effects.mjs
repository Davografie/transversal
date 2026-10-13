/**
 * Executable check for a roll-table entry's effects opening in a child panel.
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image, the same
 * way as the other checks:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-roll-table-entry-effects.mjs
 *
 * The request: "The Effects of a Roll Table Entry should open in a child panel.
 * So clicking an effect in under the Effects section of the Roll Table Entry
 * should open an Effect edit panel as a child."
 *
 * `GmRollTableEntryEditPanel` rendered `EffectEditor`, which draws the list *and*
 * an inline `EffectForm` (`.ee-inline-form`) inside the row — so an effect's
 * stacked, unbounded builder was edited in the row itself. It now draws
 * `EffectList` and opens `GmRollTableEntryEffectPanel` as a child, which is the
 * shape the SFX editor already uses.
 *
 * The rules below are lifted out of the shipping `.vue` files and run, so this is
 * the shipped logic rather than a restatement of it.
 */
import { readFileSync } from 'node:fs'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}

const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8')
const ENTRY = read('../src/components/gm/GmRollTableEntryEditPanel.vue')
const EFFECT_PANEL = read('../src/components/gm/GmRollTableEntryEffectPanel.vue')

/** The shipped text between two markers, so it can be run as written. */
function between(src, from, to) {
  const i = src.indexOf(from)
  if (i < 0) throw new Error(`not found: ${from}`)
  const j = src.indexOf(to, i)
  if (j < 0) throw new Error(`not found: ${to}`)
  return src.slice(i, j)
}

const ON_SAVE_SRC = between(EFFECT_PANEL, 'function onSave(eff)', '\nfunction close()')
const PRIOR_SRC = between(EFFECT_PANEL, 'function priorEffects()', '\nwatch(')

const runOnSave = new Function('ctx', `
  const { draft, props, panel } = ctx
  ${ON_SAVE_SRC}
  return onSave
`)
const runPrior = new Function('ctx', `
  const { draft, props } = ctx
  ${PRIOR_SRC}
  return priorEffects
`)

const eff = (name) => ({ type: 'trait', action: 'add', name })

// ── 1. the child writes into the row's draft ────────────────────────────
console.log('\nGmRollTableEntryEffectPanel — saving one effect of the row\n')

{
  let closes = 0
  const ctx = { draft: { effects: [eff('a')] }, props: { index: null }, panel: { close: () => { closes++ } } }
  runOnSave(ctx)(eff('b'))
  ok('adding appends to the row draft', ctx.draft.effects.map(e => e.name), ['a', 'b'])
  ok('adding closes the child panel (the next effect is a new form)', closes, 1)
}

{
  let closes = 0
  const ctx = { draft: { effects: [eff('a'), eff('b')] }, props: { index: 1 }, panel: { close: () => { closes++ } } }
  runOnSave(ctx)(eff('b2'))
  ok('editing replaces in place rather than appending', ctx.draft.effects.map(e => e.name), ['a', 'b2'])
  ok('editing leaves the panel open so the effect can be iterated on', closes, 0)
}

{
  // The row is a reactive object whose `effects` is replaced, exactly as the
  // entry panel's `form` is when the child assigns `draft.effects = [...]`.
  let closes = 0
  const row = { _effects: [eff('a')] }
  Object.defineProperty(row, 'effects', {
    get() { return this._effects },
    set(v) { this._effects = v },
  })
  runOnSave({ draft: row, props: { index: null }, panel: { close: () => { closes++ } } })(eff('b'))
  ok('the write lands on the row the entry panel later saves', row.effects.map(e => e.name), ['a', 'b'])
}

{
  // A child opened with no draft must not throw (it is a read-only no-op).
  let closes = 0
  const ctx = { draft: null, props: { index: null }, panel: { close: () => { closes++ } } }
  runOnSave(ctx)(eff('a'))
  ok('a missing draft is a no-op, not a crash', closes, 0)
}

// ── 2. the scope an effect sees: the ones before it ─────────────────────
console.log('\nGmRollTableEntryEffectPanel — prior effects scope the wizard\n')

ok('adding sees every existing effect as prior',
  runPrior({ draft: { effects: [eff('a'), eff('b')] }, props: { index: null } })().map(e => e.name), ['a', 'b'])
ok('editing index 1 sees only effect 0',
  runPrior({ draft: { effects: [eff('a'), eff('b'), eff('c')] }, props: { index: 1 } })().map(e => e.name), ['a'])
ok('editing index 0 sees nothing',
  runPrior({ draft: { effects: [eff('a')] }, props: { index: 0 } })(), [])
ok('no draft is an empty scope, not a crash',
  runPrior({ draft: null, props: { index: null } })(), [])

// ── 3. nothing here persists; the row's Save is the commit point ────────
console.log('\nGmRollTableEntryEffectPanel — the row owns persistence\n')

ok('the effect panel never writes to the API',
  /graphql\(|useApi|saveRollTable|updateSfx/.test(EFFECT_PANEL), false)
ok('its save is synchronous (no awaited write behind the form)',
  /async function onSave/.test(EFFECT_PANEL), false)
ok('the entry panel still persists the row through saveRollTable',
  /saveRollTable\(input\)/.test(ENTRY), true)

// ── 4. the wiring: a child panel, and no inline form ────────────────────
console.log('\nGmRollTableEntryEditPanel — the form opens as a child\n')

ok('the row draws the effects list', /<EffectList/.test(ENTRY), true)
ok('a row click opens the effect editor', /@edit="openEffectEditor"/.test(ENTRY), true)
ok('the add button opens it too', /@add="openEffectEditor\(null\)"/.test(ENTRY), true)
ok('it opens the effect panel through its own panel context',
  /panel\.open\(\{[\s\S]*?component:\s*GmRollTableEntryEffectPanel/.test(ENTRY), true)
ok('the open passes identity plus the row\'s universe/life-path scope',
  /component:\s*GmRollTableEntryEffectPanel,[\s\S]*?props:\s*\{[\s\S]*?index,[\s\S]*?universe:[\s\S]*?lifePath:/.test(ENTRY), true)
// The row itself, as the live `form` — not a copy, or the child's edits would land
// on a snapshot and the row's Save would write the stale one. Other keys may ride
// along in the same context ([[B281]] adds the resolved scope), so this asserts the
// reference rather than pinning the object literal to exactly one field.
ok('the row draft crosses in the spec context, as a live reference',
  /context:\s*\{[^}]*\browDraft:\s*form\b\s*[,}]/.test(ENTRY), true)
ok('and the row\'s resolved scope crosses with it, so its effects can use its names',
  /context:\s*\{[^}]*\bscopeVariables:/.test(ENTRY), true)
ok('the child injects that draft', /inject\('rowDraft'/.test(EFFECT_PANEL), true)
ok('the child injects the scope too', /inject\('scopeVariables'/.test(EFFECT_PANEL), true)
ok('the child renders the effect form', /<EffectForm/.test(EFFECT_PANEL), true)
ok('the form keeps the row\'s universe/life-path scope',
  /:universe="universe"/.test(EFFECT_PANEL) && /:life-path="lifePath"/.test(EFFECT_PANEL), true)
ok('the form is handed the scope as well',
  /:scope-variables="scopeVariables/.test(EFFECT_PANEL), true)
ok('the child panel is told which effect it is editing (identity only)',
  /index:\s*\{\s*type:\s*Number/.test(EFFECT_PANEL), true)

// The reported shape: the list *and* the form rendered inside the row. Both
// halves must be gone from the entry panel, or the form still opens inline.
// (`openEffectEditor` is this panel's own opener, so match the component usage,
// the import and the inline wrapper rather than the bare word.)
ok('the entry panel no longer embeds the inline effect form',
  /<EffectEditor|import EffectEditor|<EffectForm|\.ee-inline-form/.test(ENTRY), false)
ok('and no longer imports the inline editor at all',
  /from '\.\/EffectEditor\.vue'/.test(ENTRY), false)
ok('the row highlight still follows the open effect',
  /:editing-index="editingEffectIndex"/.test(ENTRY) && /onChildClose\(/.test(ENTRY), true)

console.log(`\n${pass} passed, ${fail} failed\n`)
process.exit(fail ? 1 : 0)
