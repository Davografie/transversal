/**
 * Executable check: **an owner's SFX list can author a rule, not only pick one.**
 *
 * Two surfaces do this, for the two things that own rules and show them in their
 * own editor:
 *
 *   - `GmTraitEditPanel` → *Possible SFXs* ([[B324]]) — the static half of reach:
 *     the rules a holder of the trait can buy;
 *   - `GmEntityEditPanel` → *SFX* ([[B325]]) — what this entity owns, which a
 *     place and a character both store in the same `entity.sfxIds`.
 *
 * Three classes of failure are pinned here, all of them silent:
 *
 * 1. **The ordering** (trait): `trait` re-seeds the whole form from the server, so
 *    a refresh that lands before the debounced save puts the list back and the new
 *    rule leaves it. Rule created, panel closed cleanly, nothing attached.
 * 2. **The read** (entity): the list renders from `selected.sfxIds`, so if the
 *    entity query does not *select* `sfxIds` the section is empty forever and looks
 *    like the feature never shipped.
 * 3. **The live array** (both): the picker is handed `selectedIds` as a panel prop,
 *    and `panel.open` keeps the props object **by reference**. A spread copy freezes
 *    the picker's idea of what is selected — a tick renders as nothing happening
 *    while the attach goes through — and so does replacing the array instead of
 *    splicing it.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const SRC = fileURLToPath(new URL('../src', import.meta.url))
const trait = readFileSync(`${SRC}/components/gm/GmTraitEditPanel.vue`, 'utf8')
const entity = readFileSync(`${SRC}/components/gm/GmEntityEditPanel.vue`, 'utf8')
const crud = readFileSync(`${SRC}/composables/useEntityCrud.js`, 'utf8')

let failed = 0
const ok = (name, got, want = true) => {
  const pass = got === want
  console.log(`  ${pass ? 'PASS' : 'FAIL'}  ${name}`)
  if (!pass) failed += 1
}

const body = (src, startMarker, endMarker) => {
  const a = src.indexOf(startMarker)
  const b = endMarker ? src.indexOf(endMarker, a + startMarker.length) : src.length
  return a < 0 ? '' : src.slice(a, b < 0 ? src.length : b)
}

// ── The trait editor (B324) ──────────────────────────
const tEdit = body(trait, 'function openNewSfx(', '\nfunction ')
const tCreate = body(trait, 'function createOpenNewSfx(', '\nfunction ')
const tPicker = body(trait, 'function openSfxPicker(', '\nfunction ')
const tCreatePicker = body(trait, 'function createOpenSfxPicker(', '\nfunction ')

ok('the trait list offers + New SFX on both forms',
  /@click="openNewSfx"/.test(trait) && /@click="createOpenNewSfx"/.test(trait))
ok('the trait editor opens as a child, in create mode',
  /panel\.open\(/.test(tEdit) && /props:\s*\{\s*sfx:\s*null\s*\}/.test(tEdit))
ok('the created rule is attached to the trait',
  /form\.possibleSfxIds\.push\(created\.id\)/.test(tEdit) &&
  /createForm\.possibleSfxIds\.push\(created\.id\)/.test(tCreate))

const tSave = tEdit.indexOf('await save()')
const tFetch = tEdit.indexOf('await fetchTraitsConfig()')
ok('the trait saves the declaration before refreshing — or the refresh drops it',
  tSave >= 0 && tFetch >= 0 && tSave < tFetch)
ok('the create form refreshes too (the name comes from the registry, not the id)',
  /await fetchTraitsConfig\(\)/.test(tCreate))

// The live array: a spread here is the frozen-picker bug.
ok('the trait picker is handed the live list',
  /selectedIds:\s*form\.possibleSfxIds/.test(tPicker) &&
  /selectedIds:\s*createForm\.possibleSfxIds/.test(tCreatePicker))
ok('…and edits it in place rather than replacing it',
  /possibleSfxIds\.splice\(/.test(tPicker) && /possibleSfxIds\.splice\(/.test(tCreatePicker))

// ── The entity editor (B325) ─────────────────────────
const eNew = body(entity, 'function openNewSfxForEntity(', '\nfunction ')
const ePick = body(entity, 'function openSfxPickerForEntity(', '\nfunction ')
const ePatch = body(entity, 'function patchOwnSfx(', '\n// ')

ok('the entity editor offers + Add SFX and + New SFX',
  /@click="openSfxPickerForEntity"/.test(entity) && /@click="openNewSfxForEntity"/.test(entity))
// Every entity type has the section: a `v-if` on it would silently exclude GMCs,
// factions and characters, which is most of what an author edits.
ok('the section is not gated to one entity type',
  /<div class="sfx-section">/.test(entity) &&
  !/<div v-if="[^"]*"[^>]*class="sfx-section"/.test(entity))
ok('the list renders from the entity\'s own sfxIds',
  /const ownSfxIds = computed\(\(\)\s*=>\s*selected\.value\?\.sfxIds/.test(entity))
// The read that makes it non-empty at all.
ok('the entity query selects sfxIds', /\n\s+sfxIds\s*\n/.test(crud))
// The backend gates attach on the owner kind, and a wrong kind is refused silently.
ok('the owner kind follows the entity type',
  /ownerKind = computed\(\(\)\s*=>\s*\(?form\.value\?\.type === 'LOCATION' \? 'location' : 'entity'/.test(entity))
ok('the entity picker is handed the live list, not a copy',
  /selectedIds:\s*ownSfxIds\.value/.test(ePick) && !/selectedIds:\s*\[\.\.\./.test(ePick))
ok('a write mutates the list in place', /\.splice\(at, 1\)/.test(ePatch) && /list\.push\(id\)/.test(ePatch))
ok('the new rule is attached, then the registry refreshed so it has a name',
  eNew.indexOf('await attachSfx(created.id)') >= 0 &&
  eNew.indexOf('await attachSfx(created.id)') < eNew.indexOf('await fetchTraitsConfig()'))
ok('both writes go through the owner mutations, not a form field',
  /addOwnerSfx\(/.test(entity) && /removeOwnerSfx\(/.test(entity))

console.log(failed ? `${failed} failed` : 'all clear')
process.exit(failed ? 1 : 0)
