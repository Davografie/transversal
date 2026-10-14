/**
 * Static check: the client half of an authored client action ([[B132]]).
 *
 * Effects built the emission and the wire contract in September; the client side
 * was never built, and its failure mode is the quietest kind — the event is simply
 * not in `useSSE`'s subscription list, so nothing arrives, nothing errors, and the
 * feature looks like "the rule does nothing". The same is true one step later: a
 * `recipient_id` gate that is missing means every device reacts to every other
 * device's action.
 *
 * The contract this pins is the *server's* (`src/api/…/services/client_actions.py`):
 *
 *   * the event is `client_action`, published to **every** active session, so the
 *     client filters on `recipient_id` itself;
 *   * `sticky` is **omitted unless true**, and `tap` is omitted unless it does
 *     something — so absent means "plain toast" and "no action", not "unknown";
 *   * `tap` is `"open_sheet"` (the authoring vocabulary is `none` | `open_sheet`).
 *
 * The **surface** it lands on is [[B229]]'s splash, whose target face was built for
 * the difficulty target ([[B287]]) — so this file checks that the client action
 * *joins* that face rather than growing a second one beside it.
 *
 * No browser and no dependency:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-client-actions.mjs
 */
import { readFileSync } from 'node:fs'

let pass = 0, fail = 0
/** `bad` is the list of problems; empty means pass. */
const ok = (name, bad) => {
  bad.length ? fail++ : pass++
  console.log(`  ${bad.length ? 'FAIL' : 'PASS'}  ${name}${bad.length ? `\n         ${bad.join('\n         ')}` : ''}`)
}
/** For a plain boolean: the problem is the value that failed the claim. */
const yes = (name, cond, got = '') => ok(name, cond ? [] : [String(got)])

const APP = 'src/App.vue'
const SSE = 'src/composables/useSSE.js'
const SPLASH = 'src/components/app/SplashPanel.vue'

const app = readFileSync(APP, 'utf8')
const sse = readFileSync(SSE, 'utf8')
const splash = readFileSync(SPLASH, 'utf8')

/** The `.sp-root` rule, sliced out so a claim about it cannot match the rest. */
const rootRule = (splash.match(/^\.sp-root \{[\s\S]*?\n\}/m) || [''])[0]
/** The body of a `function name(…) { … }` in App.vue, for claims about it alone. */
const fn = (name) => (app.match(new RegExp(`function ${name}\\([^)]*\\) \\{[\\s\\S]*?\\n\\}`)) || [''])[0]

// ── 1. the event arrives at all ─────────────────────────────────────────────
{
  yes('the client subscribes to client_action (absent from this list, nothing arrives)',
    /'client_action'/.test(sse))
  yes('…and the shell has a case for it',
    /case 'client_action':[\s\S]{0,200}handleClientAction\(evt\.data\)/.test(app))
  yes('…which is a function that exists', /function handleClientAction\(data\)/.test(app))
}

// ── 2. who reacts ───────────────────────────────────────────────────────────
// Published to every session, so this gate is the only thing between "the table
// gets a message" and "every device acts on everybody's actions".
{
  yes('a client that is not the recipient ignores it',
    /function handleClientAction\(data\) \{\s*if \(!data \|\| !data\.action\) return\s*if \(data\.recipient_id !== entityId\.value\) return/.test(app))
}

// ── 3. what the two actions do ──────────────────────────────────────────────
{
  const handler = fn('handleClientAction')
  yes('open_sheet focuses a sheet', /data\.action === 'open_sheet'[\s\S]{0,80}focusCharacterSheet\(data\.target_id\)/.test(handler))
  yes('an action the client does not know is ignored rather than guessed at',
    /if \(data\.action !== 'toast'\) return/.test(handler))
  yes('a non-sticky toast is the plain toast the contract says it is (absent sticky means false)',
    /if \(!data\.sticky\) \{[\s\S]{0,80}addToast/.test(handler))
  yes('a sticky one is a splash that waits', /pushSplashNote\(\{[\s\S]{0,260}sticky: true/.test(handler))
  yes('the only tap the client honours is open_sheet — the server\'s `none` | `open_sheet`',
    /data\.tap === 'open_sheet' \? 'Open character sheet' : null/.test(handler))
  yes('…and it rides the same `action` cue the target face already renders',
    /action: data\.tap === 'open_sheet'/.test(handler) && /currentNote\.action/.test(splash))
}

// ── 4. focusing a sheet works in every layout, and for somebody else ────────
// Docked (always up), the pop-out column, and the phone's band stack — the last
// one is the only place "focus" is a visible act, which is why the specs drive it
// on a phone.
{
  const focus = fn('focusCharacterSheet')
  yes('the sheet is expanded on a phone', /mobileStackActive\.value[\s\S]{0,60}setMobileFocus\('sheet'\)/.test(focus))
  yes('…and revealed in the pop-out and docked layouts',
    /else if \(!sheetDock\.value\) openPanel\(\)/.test(focus))
  yes('a target aimed at somebody else opens *their* sheet, not a pretence that it is mine',
    /viewingEntityId\.value = targetId && targetId !== entityId\.value \? targetId : null/.test(focus))
  yes('…and the tap passes the note\'s target through',
    /function onSplashAct\(note\) \{\s*advanceSplash\(\)\s*focusCharacterSheet\(note\?\.targetId\)/.test(app))
}

// ── 5. the message that waits, and the way out ──────────────────────────────
{
  yes('a sticky message gets no dwell — a report may expire, a message with an action may not',
    /function startSplashTimer\(\) \{[\s\S]{0,600}if \(splashNote\.value\?\.sticky\) return/.test(app))
  yes('a note that names an action *is* the control (a button, so it is announced and keyboard-reachable)',
    /:is="currentNote\.action \? 'button' : 'div'"/.test(splash))
  yes('…and a plain report stays a live region instead',
    /:role="currentNote\.action \? undefined : 'status'"/.test(splash))
  // No visible cue: pressing the card is the action, and a line explaining it is
  // noise (the author). The accessible name has to carry what the cue said.
  yes('the press needs no cue line, but it does keep an accessible name',
    !/sp-note-cue/.test(splash) && /:aria-label="currentNote\.action \|\| undefined"/.test(splash))
  yes('a sticky message with nothing to press carries its own way out',
    /v-if="currentNote\.sticky && !currentNote\.action"/.test(splash)
      && /@click="emit\('dismiss', currentNote\)"/.test(splash))
  yes('the ✕ sits beside the control, never inside it (a button in a button is not a thing)',
    /<div :key="currentNote\.id" class="sp-note-wrap">/.test(splash))
  yes('…and both emits are wired on the mount',
    /<SplashPanel[\s\S]{0,700}@act="onSplashAct"[\s\S]{0,120}@dismiss="advanceSplash"/.test(app))
}

// ── 6. front and centre, and still not a dialog ─────────────────────────────
{
  yes('every face opens at the centre of the viewport',
    /position: fixed/.test(rootRule) && /inset: 0/.test(rootRule) && /margin: auto/.test(rootRule))
  yes('…without a transform: a transformed ancestor re-parents position:fixed descendants',
    rootRule.length > 0 && !/transform:/.test(rootRule))
  yes('…and without a scrim or a full-viewport box (the card is the only hit target)',
    !/background: var\(--scrim\)/.test(splash))
}

// ── 7. the target face it joins is untouched ────────────────────────────────
// B287's difficulty target is the other user of this face and its own spec pins
// it; a merge that grew a second note vocabulary would pass every check above and
// still break that.
{
  yes('the difficulty target still builds its own note, on this one face',
    /function pushSplashTarget\(difficulty, dice = \[\]\)/.test(app)
      && /kind: 'target'/.test(app) && /action: 'Open character sheet'/.test(app))
  yes('…and the three kind labels survive the merge',
    /KIND_LABELS = \{ summary: 'resolved', target: 'your target', change: 'changed' \}/.test(splash))
}

// ── 8. the target is the loud one ───────────────────────────────────────────
// "The target number needs to be big and daunting" (the author). The drama has to
// stay on *descendants*: `.sp-root` must remain transform-free, because a transformed
// ancestor becomes the containing block for `position: fixed` descendants — the trap
// the landscape dock records, re-checked in §6.
{
  yes('the number is its own element, not part of the title',
    /v-if="currentNote\.value" class="sp-target"/.test(splash) && /sp-target-value/.test(splash)
      && /value: String\(difficulty\)/.test(app))
  yes('…and the head is skipped with it, so the number is not labelled twice',
    /<div v-else class="sp-note-head">/.test(splash))
  // "Big" is the requirement, so the size is checked as a floor rather than a literal:
  // a number that shrank back to body size would still pass a presence check.
  const valueSize = Number(((splash.match(/\.sp-target-value \{[\s\S]{0,600}?font-size: (\d+)px/) || [])[1] || 0))
  yes('…the number is stated large, with the accent glow and a breathing pulse',
    valueSize >= 60 && /text-shadow:/.test(splash) && /@keyframes sp-target-glow/.test(splash),
    `font-size: ${valueSize}px`)
  yes('…and the entrance is a pop plus a ring, not a fade',
    /@keyframes sp-target-pop/.test(splash) && /@keyframes sp-target-ring/.test(splash))
  yes('…behind a wash that puts the eye on the number first',
    /\.sp-target::before \{[\s\S]{0,200}radial-gradient/.test(splash))
  yes('…and the card itself is edged and glowing, so the target reads as the loud face',
    /'sp-target-card': !!currentNote\?\.value/.test(splash) && /\.sp-target-card \{/.test(splash))
  yes('the flash never lands on the fixed root', rootRule.length > 0 && !/animation:/.test(rootRule))
  yes('…and it is all off under reduced motion',
    /prefers-reduced-motion: reduce\) \{[\s\S]{0,200}\.sp-target-value, \.sp-target-ring, \.sp-chip \{ animation: none/.test(splash))
  yes('the ring is decoration: out of the flow and never eating the press',
    /\.sp-target-ring \{[\s\S]{0,300}pointer-events: none/.test(splash))
}

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
