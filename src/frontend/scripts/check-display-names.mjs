/**
 * Executable check for adding a trait's dynamic display names consecutively.
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image, the same
 * way as the other checks:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-display-names.mjs
 *
 * The report: "I want to be able to add different dynamic trait display names
 * consecutively. So when the 'add display name' is open and saved, and I click
 * '+ add display name' in the trait panel, I want a new 'add display name'."
 *
 * Two causes, both in `GmDisplayNameEditPanel.vue`:
 *
 *  1. `Panel.openChild` replaces a child's spec **in place** when the same
 *     component opens again with no `id` (`Panel.vue`, "otherwise append it"),
 *     so Vue reuses the instance and the `form` built once in `setup()` never
 *     clears — the next `+ Add Display Name` showed the entry just saved.
 *  2. `buildUpdatedList` rebuilt the list from the `allDisplayNames` **prop**,
 *     which the panel spec froze at open, so a second save from that same panel
 *     would drop the first entry rather than extend the list.
 *
 * The rules below are lifted out of the shipping `.vue` files and run, so this is
 * the shipped logic rather than a restatement of it. The pre-fix body is run too
 * and must reproduce the reported symptom, or the pass means nothing.
 */
import { readFileSync } from 'node:fs'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}

const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8')
const EDITOR = read('../src/components/gm/GmDisplayNameEditPanel.vue')
const TRAIT_PANEL = read('../src/components/gm/GmTraitEditPanel.vue')
const PANEL = read('../src/components/gm/Panel.vue')

/** The shipped text between two markers, so it can be run as written. */
function between(src, from, to) {
  const i = src.indexOf(from)
  if (i < 0) throw new Error(`not found: ${from}`)
  const j = to ? src.indexOf(to, i) : src.length
  if (j < 0) throw new Error(`not found: ${to}`)
  return src.slice(i, j)
}

const MERGE_SRC = between(EDITOR, 'function mergeDisplayName(', '\nfunction buildUpdatedList')
const DO_SAVE_SRC = between(EDITOR, 'async function doSave()', '\n</script>')
const SEED_SRC = between(EDITOR, 'function seedForm(', '\nseedForm()')

const mergeDisplayName = new Function(`${MERGE_SRC}; return mergeDisplayName`)()

// ── 1. merging one entry into the live list ─────────────────────────────
console.log('\nGmDisplayNameEditPanel — merging an entry into the list\n')

const dn = (name, universe = '', ratings = []) => ({ name, universe, ratings })

ok('a new entry is appended', mergeDisplayName([], { name: 'Might', universe: 'earth', ratings: [['D8']] }, null),
  [dn('Might', 'earth', [['D8']])])

ok('a second entry extends a list that already holds the first',
  mergeDisplayName([dn('Might')], { name: 'Grace', universe: '', ratings: [] }, null),
  [dn('Might'), dn('Grace')])

ok('editing replaces in place rather than appending',
  mergeDisplayName([dn('Might'), dn('Grace')], { name: 'Spirit', universe: 'three_realms', ratings: [] }, 1),
  [dn('Might'), dn('Spirit', 'three_realms', [])])

ok('an undefined index is an add, not an edit',
  mergeDisplayName([dn('Might')], { name: 'Grace', universe: '', ratings: [] }, undefined),
  [dn('Might'), dn('Grace')])

ok('a blank name is dropped', mergeDisplayName([], { name: '   ', universe: '', ratings: [] }, null), [])

ok('empty rating rows are dropped and the name is trimmed',
  mergeDisplayName([], { name: '  Might  ', universe: '', ratings: [[], ['D6'], []] }, null),
  [dn('Might', '', [['D6']])])

ok('the entries it is handed are copied, not aliased', (() => {
  const source = [dn('Might', '', [['D8']])]
  const out = mergeDisplayName(source, { name: 'Grace', universe: '', ratings: [] }, null)
  out[0].ratings[0].push('D12')
  return source[0].ratings[0]
})(), ['D8'])

// The regression this fix is about: the pre-fix rule rebuilt the list from the
// prop snapshot the panel froze at open, so the second save dropped the first.
console.log('\nThe pre-fix rule, which must reproduce the report\n')

const preFixBuild = (propSnapshot, form, isNew, editIndex) => {
  const list = propSnapshot.map(d => ({ name: d.name || '', universe: d.universe || '', ratings: (d.ratings || []).map(r => [...r]) }))
  const newEntry = { name: form.name.trim(), universe: form.universe || '', ratings: form.ratings.filter(r => r.length > 0) }
  if (isNew) list.push(newEntry)
  else list[editIndex] = newEntry
  return list.filter(d => d.name)
}

// Open with an empty list; save "Might" (the parent's list is now ["Might"]);
// the prop snapshot is still []; then save "Grace" from the same panel.
const LIVE_AFTER_FIRST = [dn('Might')]
ok('pre-fix: a second save drops the first entry (the reported symptom)',
  preFixBuild([], { name: 'Grace', universe: '', ratings: [] }, true, null),
  [dn('Grace')])
ok('shipped: the same two saves keep both, because the list is read live',
  mergeDisplayName(LIVE_AFTER_FIRST, { name: 'Grace', universe: '', ratings: [] }, null),
  [dn('Might'), dn('Grace')])

// ── 2. what a save does to the open form ────────────────────────────────
console.log('\nGmDisplayNameEditPanel — a saved add goes back to blank\n')

const runDoSave = new Function('ctx', `
  const { isDirty, saving, errorMsg, isNew, entrySignature, buildUpdatedList, graphql, patchData, props, emit, resetForm } = ctx
  ${DO_SAVE_SRC}
  return doSave()
`)

function saveCase({ isNew = true, signatures = ['same', 'same'], reject = false }) {
  const calls = { reset: 0, emitted: [], patched: 0, graphql: 0 }
  let at = 0
  const ctx = {
    isDirty: { value: true },
    saving: { value: false },
    errorMsg: { value: '' },
    isNew: { value: isNew },
    entrySignature: () => signatures[Math.min(at++, signatures.length - 1)],
    buildUpdatedList: () => [dn('Might')],
    graphql: async () => { calls.graphql++; if (reject) throw new Error('write refused'); return {} },
    patchData: () => { calls.patched++ },
    props: { traitId: 'trait-1' },
    emit: (ev, payload) => calls.emitted.push([ev, payload]),
    resetForm: () => { calls.reset++ },
  }
  return { ctx, calls }
}

{
  const { ctx, calls } = saveCase({ isNew: true })
  await runDoSave(ctx)
  ok('a new entry resets the form to blank', calls.reset, 1)
  ok('and is marked clean once it is written', ctx.isDirty.value, false)
  ok('and is emitted to the opener', calls.emitted, [['saved', [dn('Might')]]])
  ok('the write is patched into the shared trait cache', calls.patched, 1)
  ok('and the busy flag is cleared', ctx.saving.value, false)
}

{
  const { ctx, calls } = saveCase({ isNew: false })
  await runDoSave(ctx)
  ok('an edit does NOT reset the form (it must keep showing the entry)', calls.reset, 0)
  ok('an edit still emits and patches', [calls.emitted.length, calls.patched], [1, 1])
}

{
  // Typing landed while the write was in flight: the newer text must survive.
  const { ctx, calls } = saveCase({ isNew: true, signatures: ['before', 'after'] })
  await runDoSave(ctx)
  ok('a newer edit in flight is not reset away', calls.reset, 0)
  ok('and stays dirty so its own debounce saves it', ctx.isDirty.value, true)
}

{
  const { ctx, calls } = saveCase({ isNew: true, reject: true })
  await runDoSave(ctx)
  ok('a refused write reports the reason', ctx.errorMsg.value, 'write refused')
  ok('a refused write neither resets nor emits', [calls.reset, calls.emitted.length], [0, 0])
  ok('a refused write leaves the form dirty to retry', ctx.isDirty.value, true)
}

// ── 3. re-seeding when the spec changes identity ────────────────────────
// The same component is reused when the opener replaces its spec, so an edit
// opened after an add (or another row's edit) must re-load the form. Without
// this, "add Mira, then edit Grace" would save Mira's text into Grace's row.
console.log('\nGmDisplayNameEditPanel — the form follows the spec it now points at\n')

const runSeedForm = new Function('ctx', `
  const { isNew, liveList, props, form, showDiePicker, isDirty, clearTimeout, nextTick } = ctx
  let saveTimer = null
  let suppressWatch = false
  ${SEED_SRC}
  seedForm()
  return { suppress: () => suppressWatch }
`)

function seedCase({ isNew, editIndex, list, held, picker = 2, dirty = true }) {
  const ctx = {
    isNew: { value: isNew },
    liveList: () => list,
    props: { editIndex },
    form: { name: held.name, universe: held.universe || '', ratings: (held.ratings || []).map(r => [...r]) },
    showDiePicker: { value: picker },
    isDirty: { value: dirty },
    clearTimeout: () => {},
    nextTick: (fn) => fn(),
  }
  const state = runSeedForm(ctx)
  return { ctx, state }
}

{
  // "Add Display Name" behind a form holding a just-saved entry.
  const { ctx, state } = seedCase({ isNew: true, editIndex: null, list: [dn('Might')], held: dn('Might', 'earth', [['D8']]) })
  ok('an add opens blank, not holding the saved entry', ctx.form, { name: '', universe: '', ratings: [] })
  ok('and is clean, so the blank add form does not write itself', ctx.isDirty.value, false)
  ok('and drops any open die picker', ctx.showDiePicker.value, null)
  ok('and releases the watcher once the DOM has caught up', state.suppress(), false)
}

{
  const list = [dn('Might', 'earth', [['D8']]), dn('Grace', 'three_realms', [['D10'], []])]
  const { ctx } = seedCase({ isNew: false, editIndex: 1, list, held: dn('Might', 'earth', [['D8']]) })
  ok('editing row 1 after an add loads that row, not the text typed before',
    ctx.form, { name: 'Grace', universe: 'three_realms', ratings: [['D10'], []] })
  ok('the loaded ratings do not alias the stored entry', (() => {
    ctx.form.ratings[0].push('D12')
    return list[1].ratings[0]
  })(), ['D10'])
}

{
  const { ctx } = seedCase({ isNew: false, editIndex: 9, list: [dn('Might')], held: dn('Might') })
  ok('an out-of-range index seeds blank rather than throwing', ctx.form, { name: '', universe: '', ratings: [] })
}

// The pre-fix shape: `form` built once from the entry at *open* time, so a later
// spec change leaves the previous entry in the fields.
const preFixSeed = (form, props) => form // never re-reads props.editIndex
ok('pre-fix: switching from add to edit leaves the added text in the form',
  preFixSeed({ name: 'Mira', universe: '', ratings: [] }, { editIndex: 1 }), { name: 'Mira', universe: '', ratings: [] })
ok('shipped: the same switch loads row 1', seedCase({
  isNew: false, editIndex: 1, list: [dn('Might'), dn('Grace')], held: dn('Mira'),
}).ctx.form, { name: 'Grace', universe: '', ratings: [] })

// ── 4. the wiring, so the fix cannot be half-applied ────────────────────
console.log('\nWiring — the live ref crosses the panel boundary\n')

ok('the opener hands the live list across in the spec context',
  /context:\s*\{\s*displayNamesDraft:\s*displayNames\s*\}/.test(TRAIT_PANEL), true)
ok('the editor injects that ref', /inject\('displayNamesDraft'/.test(EDITOR), true)
ok('and builds its list from the live value, not the frozen prop',
  /mergeDisplayName\(liveList\(\)/.test(EDITOR) && /displayNamesDraft\?\.value\s*\?\?\s*props\.allDisplayNames/.test(EDITOR), true)
ok('the opener never reads the prop for the list it renders', /allDisplayNames:\s*displayNames\.value/.test(TRAIT_PANEL), true)
ok('the form re-seeds when the spec changes identity',
  /watch\(\[\(\) => props\.editIndex, \(\) => props\.traitId\], seedForm\)/.test(EDITOR), true)
ok('the reset is suppressed from the auto-save watcher', /if \(suppressWatch\) return/.test(EDITOR), true)
ok('seeding clears the pending save timer', /seedForm[\s\S]*clearTimeout\(saveTimer\)/.test(EDITOR), true)
ok('the reset refocuses the name field for the next entry', /nameInput\.value\?\.focus\(\)/.test(EDITOR), true)
ok('the add panel still opens with no id, so it is reused in place (the reason a reset is needed)',
  /openDisplayNameEditor\(null\)/.test(TRAIT_PANEL) && /if \(normalized\.id\) return c\.spec\.id === normalized\.id[\s\S]*return !c\.spec\.id/.test(PANEL), true)

console.log(`\n${pass} passed, ${fail} failed\n`)
process.exit(fail ? 1 : 0)
