/**
 * Executable check for the portal-effects panel's auto-save.
 *
 * The author's request, relayed through [[effects]] on 2026-10-17: *"The portal
 * effects panels should have auto-save."* It was the last authoring panel with a
 * manual Save, and the save **was** the close: `save()` POSTed and then called
 * `panel.close()`.
 *
 * Run it against the frontend image, the same way as the other checks:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-portal-autosave.mjs
 *
 * The three rules are the ones `GmRollTableEditPanel` writes down at length, and
 * each is asserted here because each is silent when broken:
 *   1. the **whole draft** is watched, not a list of field names (a list falls
 *      behind, and a field that never saves reads as "auto-save is broken");
 *   2. a **pending write is flushed on close** — with the button gone, a close
 *      inside the debounce window drops the last edit with no trace;
 *   3. the parent's copy is kept in step by **every** write, not only on the way
 *      out, or its summary goes stale while you work.
 *
 * This is a source check: a Vue component is not reachable from node. The browser
 * half — that the panel has no Save button and that an edit really reaches the
 * endpoint, including one made just before closing — is
 * `e2e/tests/portal-autosave.spec.js`.
 */
import { readFileSync } from 'node:fs'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}

const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8')
const PANEL = read('../src/components/gm/GmPortalConfigPanel.vue')

// ── 1. the button is gone, and so is the close ──────────────────────────
console.log('\nthere is no Save button, and saving no longer closes the panel\n')

ok('no Save button is rendered', /class="save-btn"/.test(PANEL), false)
ok('and no Cancel button either — the rail closes a panel', /class="cancel-btn"/.test(PANEL), false)
// Scoped to the function: the block comment above the script *describes* the old
// `panel.close()`, so a whole-file grep for it passes for the wrong reason.
ok('the save no longer closes the panel',
  !/panel\.close\(\)/.test(PANEL.slice(PANEL.indexOf('async function save()'))), true)
// It opens the child panel with it — but never closes itself with it, which is
// the assertion just above.
ok('the panel context is used to open the child panel', /panel\.open\(/.test(PANEL), true)
// A button used to be the only feedback that a write happened.
ok('something still says so — the write is visible while it is in flight',
  /Saving…/.test(PANEL) && /is-saved/.test(PANEL) && /savedAt\.value = Date\.now\(\)/.test(PANEL), true)

// ── 2. the draft is seeded before the watcher exists ────────────────────
console.log('\nloading is not an edit\n')

{
  const seed = PANEL.indexOf('const draft = reactive({ effects: (props.link.effects')
  const watchAt = PANEL.indexOf('watch(draft, scheduleSave')
  ok('the draft is seeded at all', seed > 0, true)
  ok('and the watcher is registered after the seeding, so the first copy is not an edit',
    seed > 0 && watchAt > seed, true)
}

// ── 3. the three rules ──────────────────────────────────────────────────
console.log('\nthe three rules of the house pattern\n')

ok('the whole draft is watched, deeply — not a list of field names',
  /watch\(draft, scheduleSave, \{ deep: true, flush: 'sync' \}\)/.test(PANEL), true)
ok('behind a debounce',
  /clearTimeout\(_saveTimer\)[\s\S]{0,80}setTimeout\(\(\) => \{ save\(\) \}, \d+\)/.test(PANEL), true)
ok('a pending write is flushed on close',
  /onUnmounted\(\(\) => \{[\s\S]{0,220}clearTimeout\(_saveTimer\)[\s\S]{0,80}save\(\)/.test(PANEL), true)
ok('and the guard makes the flush idempotent (a fired timer is nulled first)',
  /if \(_saveTimer\) \{[\s\S]{0,120}_saveTimer = null/.test(PANEL), true)
ok('the parent copy is kept in step by every write, not only on the way out',
  /props\.link\.effects = draft\.effects/.test(PANEL), true)
ok('and that line is inside the save, after the response is accepted',
  (() => {
    const save = PANEL.slice(PANEL.indexOf('async function save()'))
    const okCheck = save.indexOf('if (!r.ok) throw')
    const assign = save.indexOf('props.link.effects = draft.effects')
    return okCheck > 0 && assign > okCheck
  })(), true)
ok('a rejected write is reported rather than swallowed', /catch \(e\) \{[\s\S]{0,120}console\.error/.test(PANEL), true)

// ── 4. the write stays narrow ───────────────────────────────────────────
// The endpoint is a patch upsert: `effects` is written only when present, and the
// write is mirrored onto the reverse edge. Sending the edge's *mode* back is what
// would make this a read-modify-write of the document, which is the shape that
// destroyed content in [[B273]] — so the body carries nothing but identity and the
// array being edited.
console.log('\nthe write carries only what it edits\n')

ok('the body carries the edge type of the *lookup* and the effects, nothing else',
  /body: JSON\.stringify\(\{ type: 'transversal', effects: draft\.effects \}\)/.test(PANEL), true)
// Scoped to the body on purpose: the panel *reads* `link.transversal_type` to draw
// the head, so a whole-file grep for the name would pass for the wrong reason.
ok('it never rewrites the mode', (() => {
  const body = /body: JSON\.stringify\(\{([^}]*)\}\)/.exec(PANEL)
  return !!body && !body[1].includes('transversal_type')
})(), true)

// ── 5. the effect is edited in a child panel ────────────────────────────
// It was the last list still edited **inline** (`EffectEditor`). Every other one
// opens a child panel — the SFX editor's `GmEffectEditPanel`, a roll-table row's
// and a life-path step's `GmDraftEffectPanel` — because an effect is a stacked
// builder of unbounded height and the list has to stay in view while one is
// edited. `GmDraftEffectPanel` is deliberately draft-agnostic: it edits whatever
// `effects` array the opener hands it in the spec's `context`.
console.log('\nthe list stays in view: one effect is edited in a child panel\n')

const DRAFT = read('../src/components/gm/GmDraftEffectPanel.vue')

ok('the panel renders the list, not an inline editor',
  /<EffectList/.test(PANEL) && /<EffectEditor/.test(PANEL), false)
ok('and the list is wired to the draft it owns',
  /:model-value="draft\.effects"/.test(PANEL) && /@update:model-value="draft\.effects = \$event"/.test(PANEL), true)
ok('a row opens the shared child panel',
  /component: GmDraftEffectPanel/.test(PANEL), true)
ok('which one — add or edit — is the index it is given',
  /openEffectEditor\(index\)[\s\S]{0,200}index === null \? 'Add effect' : 'Edit effect'/.test(PANEL), true)
ok('the draft travels as a live reference through the spec context, which is the only way in',
  /context: \{ rowDraft: draft \}/.test(PANEL), true)
ok('and the panel writes into it rather than persisting anything itself',
  /if \(adding\) \{[\s\S]{0,80}draft\.effects = \[\.\.\.draft\.effects, eff\]/.test(DRAFT), true)
// The four portal-only props are what let the targeting wizard offer
// portal-relative targets. A straight swap to the shared panel would have dropped
// them silently, so both the passing and the forwarding are asserted.
ok('the portal destination travels with the form',
  /portalDestination: props\.link\.name/.test(PANEL)
  && /portalTargetType: props\.link\.type/.test(PANEL)
  && /portalUniverse: props\.link\.current_universe/.test(PANEL)
  && /portalRootId: props\.link\.type === 'location' \? props\.link\._key : ''/.test(PANEL), true)
ok('and the shared panel forwards them to the form, empty by default for its other two consumers',
  /portalDestination: \{ type: String, default: '' \}/.test(DRAFT)
  && /:portal-destination="portalDestination"/.test(DRAFT)
  && /:portal-root-id="portalRootId"/.test(DRAFT), true)

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
