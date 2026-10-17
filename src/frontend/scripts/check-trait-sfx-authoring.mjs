/**
 * Executable check: **a trait's SFX list can author a rule, not only pick one.**
 *
 * The list (`GmTraitEditPanel` → *Possible SFXs*) offers `+ Add SFX`, which opens
 * the picker; authoring a new rule was two panels deep (picker → `+ New SFX`).
 * `+ New SFX` here opens the editor directly as a **child panel** and attaches the
 * result to the trait's `possibleSfxIds` — the declaration half of reach.
 *
 * The load-bearing part is the **order** in edit mode: `trait` re-seeds the whole
 * form from the server (`watch(trait, …)`), so a refresh that lands before the save
 * puts the list back the way it was and the new rule silently leaves it. That is
 * the "auto-save dropped my edit" shape gm-panels documented, one panel over — and
 * it is invisible, because the rule *was* created and the panel closed cleanly.
 *
 * So the assertions are: the affordance is wired on both surfaces, the editor opens
 * in create mode as a child, the id lands in the right form, and **save precedes
 * refresh** wherever a trait exists to save.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const SRC = fileURLToPath(new URL('../src', import.meta.url))
const panel = readFileSync(`${SRC}/components/gm/GmTraitEditPanel.vue`, 'utf8')

let failed = 0
const ok = (name, got, want = true) => {
  const pass = got === want
  console.log(`  ${pass ? 'PASS' : 'FAIL'}  ${name}`)
  if (!pass) failed += 1
}

const body = (startMarker, endMarker) => {
  const a = panel.indexOf(startMarker)
  const b = endMarker ? panel.indexOf(endMarker, a + startMarker.length) : panel.length
  return a < 0 ? '' : panel.slice(a, b < 0 ? panel.length : b)
}

// The two handlers, by name. `\nfunction ` is the boundary: these are top-level
// declarations in `<script setup>`, so the next one ends the previous one.
const edit = body('function openNewSfx(', '\nfunction ')
const create = body('function createOpenNewSfx(', '\nfunction ')

// ── The affordance exists on both surfaces ───────────
// Edit mode and create mode are separate form objects, and the create one renders
// its own list — wiring only one leaves half the surface with the old two-step.
ok('the edit-mode list offers + New SFX', /@click="openNewSfx"/.test(panel))
ok('the create-mode list offers + New SFX', /@click="createOpenNewSfx"/.test(panel))
ok('+ Add SFX is still there — picking and authoring are both wanted',
  /@click="openSfxPicker"/.test(panel) && /@click="createOpenSfxPicker"/.test(panel))

// ── It opens the editor, in create mode, as a CHILD ──
// `panel.open` nests; a `replace` would throw away the trait the author is editing.
ok('the editor opens as a child panel', /panel\.open\(/.test(edit) && /panel\.open\(/.test(create))
ok('…in create mode (no existing sfx handed over)',
  /props:\s*\{\s*sfx:\s*null\s*\}/.test(edit) && /props:\s*\{\s*sfx:\s*null\s*\}/.test(create))
ok('…the editor component it opens', /component:\s*GmSfxEditPanel/.test(edit))

// ── The created rule is attached ─────────────────────
// Attaching is the whole point: a rule authored from a trait that is not on the
// trait is a rule nobody can buy, and the list it was authored from stays empty.
ok('edit mode attaches to the trait\'s own form', /form\.possibleSfxIds\.push\(created\.id\)/.test(edit))
ok('create mode attaches to the create form', /createForm\.possibleSfxIds\.push\(created\.id\)/.test(create))

// ── Save precedes refresh, or the attachment is lost ──
// This is the assertion that would have caught the silent version of this feature.
const iSave = edit.indexOf('await save()')
const iFetch = edit.indexOf('await fetchTraitsConfig()')
ok('edit mode writes the declaration at all', iSave >= 0, true)
ok('…and refreshes, so the row can render by name', iFetch >= 0, true)
ok('…in that order — the refresh re-seeds the form from the server',
  iSave >= 0 && iFetch >= 0 && iSave < iFetch)
ok('create mode refreshes too (the name comes from the registry, not the id)',
  /await fetchTraitsConfig\(\)/.test(create))

// The list renders from the SFX registry, which is why the id alone is not enough.
ok('the list is a filter over the fetched SFX, not the ids it holds',
  /const possibleSfxs = computed\(\(\)\s*=>\s*allSfxs\.value\.filter/.test(panel))

console.log(failed ? `${failed} failed` : 'all clear')
process.exit(failed ? 1 : 0)
