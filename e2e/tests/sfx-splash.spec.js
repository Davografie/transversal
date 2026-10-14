// B229 / B230 — the activation splash: the engine's two kinds of interruption.
//
// One surface, two faces. A **prompt** (an automatic or routed rule's question,
// B230's host until this migration) waits for an interaction and has no timer. A
// **note** reports what an activation did — including why an effect did nothing
// (B236) — and *fades*: a brief banner for a change, longer for a rule that has
// run its course, one at a time so a burst is not a stack of dialogs. A note
// carrying an **authored action** ([[B132]]) is the exception on both counts — it
// waits for the player, and tapping it does the authored thing. That is the same
// face the difficulty target uses ([[B287]]), which has its own spec.
//
// **Every face opens front and centre** (the author: *"I expected the splash panel
// to open front and center, but it's more like a glorified toast now"*). The
// assertion that used to pin the opposite — `centreIsPanel === false`, "a corner
// card" — is re-expressed rather than dropped: the card is now *at* the centre,
// and what must not change is that it is still **not a dialog** (no scrim, nothing
// blocked, the table outside it reachable, the sheet readable behind it).
//
// The routing rule is the author's: a manual press asks on the sheet, a roll asks
// in the roller, and an automatic rule — a state change or a timer nobody pressed
// — asks in a floating panel, because there is no obvious place its reader is
// looking. The server tags every choice with `origin`; the shell routes by it.
//
// What only a browser can show is the *host*, and each of its failure modes is
// quiet: the question falling through to the roller (where a reader who is not
// rolling will never look), a panel that dims or blocks the table it is asking
// about, one that dismisses itself before it is read, a sticky message that
// vanishes mid-reach, or an answer that loses its origin so the follow-up lands
// somewhere else. So this spec raises real events over the SSE connection and
// measures the result.
//
// The events are served as canned SSE bodies rather than by firing a rule: the
// automatic path needs authored content and a real state change, and this spec is
// about where the question renders. Writing is stubbed and every write is
// asserted on, so a run answers nothing.

import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { asPlayer } from '../helpers/role.js'
import { establishSession } from '../helpers/session.js'

const KAEL = 'character-kael-drift-e555ccde'
// The app keeps polling while the page is open, and a route callback that fires
// after the test has ended fails the *test* with a teardown error (misleading:
// it looks like a request fault). Release the routes at the end of each case.
test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})

const DESKTOP = { width: 1280, height: 950 }
const PHONE = { width: 390, height: 844 }

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: KAEL }
})

/**
 * The question an automatic rule would raise. `count: 1`, so picking a candidate
 * *is* the answer (the wizard commits without a separate confirm) and one click
 * exercises the whole answer path.
 */
const AUTO_CHOICE = {
  origin: 'auto',
  structured: true,
  element: 'trait',
  candidates: [
    { id: 'trait-e2e-a', name: 'Iron Roots', subtitle: 'a place' },
    { id: 'trait-e2e-b', name: 'Ash Road', subtitle: 'a place' },
  ],
  count: 1,
  field: 'target',
  step_index: 0,
  source_kind: 'sfx',
  source_id: 'sfx-e2e-auto',
  source_sfx_id: 'sfx-e2e-auto',
  answers_so_far: [],
}

/**
 * Serve SSE frames, then keep the stream quiet on every reconnect (the browser
 * retries when a fulfilled body ends, and re-serving the event would resurrect a
 * question the test has already left behind).
 *
 * **The frames are held until `load()` arms them**, and that is not a nicety. The
 * app opens the stream several times per load — this spec navigates twice to get a
 * SEC-3 session, and a one-shot body makes the browser retry — so serving on the
 * *first* connection is a race: measured, the frames could land on a connection the
 * app then replaced, and the note was never seen (a case that passed on
 * `release-build` and failed here purely on connection timing). Arming immediately
 * before the final navigation puts them on the connection being watched.
 *
 * `events` is the general form — `[{ type, data }]` — for anything that is not a
 * choice or an effect note: the authored client action.
 */
async function stubStream(page, choices = [AUTO_CHOICE], notes = [], events = []) {
  let armed = false
  page.__armStream = () => { armed = true }
  await page.route('**/api/v1/stream*', async (route) => {
    const headers = { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' }
    if (!armed) return route.fulfill({ status: 200, headers, body: ': idle\n\n' })
    armed = false
    const frames = []
    if (choices) frames.push(`event: sfx_choice_required\ndata: ${JSON.stringify({ entity_id: KAEL, choices })}\n\n`)
    for (const note of notes) frames.push(`event: effects_changed\ndata: ${JSON.stringify(note)}\n\n`)
    for (const ev of events) frames.push(`event: ${ev.type}\ndata: ${JSON.stringify(ev.data)}\n\n`)
    return route.fulfill({ status: 200, headers, body: frames.join('') })
  })
}

/** Record the answer mutation instead of performing it. */
async function stubAnswer(page, extras) {
  await page.route('**/api/v1/graphql', async (route) => {
    const body = route.request().postData() || ''
    if (body.includes('resolveEffectTargets(')) {
      extras.answered = JSON.parse(body).variables
      return route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({ data: { resolveEffectTargets: { applied: [], pendingChoices: [], structured: [] } } }),
      })
    }
    return route.continue()
  })
}

/** Uncaught errors and Vue warnings fail the case: a host that throws on a
 *  click looks exactly like a host that ignored it. */
function watch(page) {
  const problems = []
  page.on('pageerror', (e) => problems.push('uncaught: ' + String(e)))
  page.on('console', (m) => {
    if (m.type() === 'error' && /\[Vue warn\]/.test(m.text())) problems.push(m.text())
  })
  return problems
}

async function load(page, size) {
  await page.unroute('**/api/v1/players/**')
  await asPlayer(page)
  await page.setViewportSize(size)
  await page.goto('/')
  await page.evaluate(([pid, pname, eid]) => {
    localStorage.setItem('playerId', pid)
    localStorage.setItem('playerName', pname)
    localStorage.setItem('entityId', eid)
  }, [character.playerId, character.playerName, character.entityId])
  await establishSession(page)
  page.__armStream?.()
  await page.goto('/')
  await page.locator('.name-entry.panel').first().waitFor({ state: 'hidden', timeout: 20000 })
}

const boxOf = (page, sel) => page.evaluate((s) => {
  const el = document.querySelector(s)
  if (!el) return null
  const b = el.getBoundingClientRect()
  return { x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height), right: Math.round(b.right), bottom: Math.round(b.bottom) }
}, sel)

/** How far the splash's centre sits from the viewport's, in px. */
const offCentre = (page) => page.evaluate(() => {
  const b = document.querySelector('.sp-root')?.getBoundingClientRect()
  if (!b) return { dx: null, dy: null }
  return {
    dx: Math.round(b.x + b.width / 2 - window.innerWidth / 2),
    dy: Math.round(b.y + b.height / 2 - window.innerHeight / 2),
  }
})

test('an automatic rule asks in a floating panel, and the roller does not show it', async ({ page }) => {
  const problems = watch(page)
  const extras = {}
  await stubStream(page)
  await stubAnswer(page, extras)
  await load(page, DESKTOP)

  const panel = page.locator('.sp-root')
  await expect(panel).toBeVisible({ timeout: 15000 })
  // The wizard is the content; the host only positions it.
  await expect(page.locator('.sp-prompt .etw-root')).toBeVisible()
  await expect(panel.locator('.etw-title')).toHaveText('A rule needs a choice')
  // …and it is *only* here: `origin: auto` must not fall through to the roller,
  // whose reader is looking at a pool, not at a question about the world.
  await expect(page.locator('.sfx-choice-panel')).toHaveCount(0)

  // Front and centre now — and still **not a dialog**. Both halves matter: the
  // centre is where the author wanted it, and a scrim or a full-viewport box would
  // hide the table the question is about.
  const geometry = await page.evaluate(() => {
    const fcp = document.querySelector('.sp-root').getBoundingClientRect()
    const cx = Math.round(window.innerWidth / 2)
    const cy = Math.round(window.innerHeight / 2)
    return {
      dx: Math.round(fcp.x + fcp.width / 2 - cx),
      dy: Math.round(fcp.y + fcp.height / 2 - cy),
      areaShare: (fcp.width * fcp.height) / (window.innerWidth * window.innerHeight),
      outsideIsFree: !document.elementFromPoint(24, cy)?.closest('.sp-root'),
      sheetVisible: !!document.querySelector('.sheet-embedded')?.offsetParent,
    }
  })
  expect(Math.abs(geometry.dx), 'centred horizontally').toBeLessThanOrEqual(2)
  expect(Math.abs(geometry.dy), 'centred vertically').toBeLessThanOrEqual(2)
  expect(geometry.areaShare, 'a card in the middle, not a full-screen dialog').toBeLessThan(0.35)
  expect(geometry.outsideIsFree, 'no scrim — the table outside it is still reachable').toBe(true)
  expect(geometry.sheetVisible, 'the sheet stays readable behind the question').toBe(true)
})

test('it never answers itself, and leaving it writes nothing', async ({ page }) => {
  const problems = watch(page)
  const extras = {}
  await stubStream(page)
  await stubAnswer(page, extras)
  await load(page, DESKTOP)

  await expect(page.locator('.sp-root')).toBeVisible({ timeout: 15000 })
  // No timer: a question nobody asked for waits to be read. If a dismissal timer
  // ever creeps in, this is the assertion that catches it.
  await page.waitForTimeout(2500)
  await expect(page.locator('.sp-root')).toBeVisible()

  await page.locator('.sp-prompt .etw-cancel').click()
  await expect(page.locator('.sp-root')).toHaveCount(0)
  // Nothing was answered and nothing was written — the branch stays parked
  // server-side, which is what makes "answering nothing" a legitimate default.
  expect(extras.answered, 'leaving the question sent no mutation').toBeUndefined()
  expect(problems, problems.join('\n')).toEqual([])
})

test('answering carries the origin back, so a follow-up lands here', async ({ page }) => {
  const problems = watch(page)
  const extras = {}
  await stubStream(page)
  await stubAnswer(page, extras)
  await load(page, DESKTOP)

  await expect(page.locator('.sp-root')).toBeVisible({ timeout: 15000 })
  // A single-choice step commits on the pick — the click *is* the answer.
  await page.locator('.sp-prompt .etw-candidate').first().click()
  await expect(page.locator('.sp-root')).toHaveCount(0)

  await expect.poll(() => extras.answered?.origin).toBe('auto')
  expect(extras.answered?.resolutions?.[0]?.answers?.[0]?.ids).toEqual(['trait-e2e-a'])
  expect(extras.answered?.entityId).toBe(KAEL)
  expect(problems, problems.join('\n')).toEqual([])
})

test('on a phone it is front and centre too, whole and inside the viewport', async ({ page }) => {
  const problems = watch(page)
  const extras = {}
  await stubStream(page)
  await stubAnswer(page, extras)
  await load(page, PHONE)

  const panel = page.locator('.sp-root')
  await expect(panel).toBeVisible({ timeout: 15000 })
  await expect(page.locator('.sfx-choice-panel')).toHaveCount(0)

  // Front and centre on a phone too: the same place to look, whatever the layout
  // (it used to take the top as a banner, because the band stack owns the bottom).
  const b = await boxOf(page, '.sp-root')
  expect(Math.abs(b.x + b.w / 2 - PHONE.width / 2), 'centred horizontally').toBeLessThanOrEqual(2)
  expect(Math.abs(b.y + b.h / 2 - PHONE.height / 2), 'centred vertically').toBeLessThanOrEqual(2)
  expect(b.bottom, 'and fits on screen').toBeLessThanOrEqual(PHONE.height)
  expect(b.w, 'using most of the width').toBeGreaterThan(PHONE.width - 60)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow, 'no horizontal overflow').toBeLessThanOrEqual(0)
})

// ── the note face: what an activation did ───────────────────────────────────
//
// Aimed at the player it happened *to*: the entity they are acting as, or the
// place they are standing in.

const CHANGE_NOTE = {
  entity_id: KAEL,
  title: 'Hinder',
  kind: 'change',
  lines: [
    { text: 'play_as_rating: trait-114764719 plays as d4' },
    { text: 'no trait instance to move (unset)', silent: true },
  ],
}
const SUMMARY_NOTE = { entity_id: KAEL, title: 'Gift', kind: 'summary', lines: [{ text: 'step_up: die stepped to d8' }] }

test('a note splashes what changed, and fades', async ({ page }) => {
  await stubStream(page, null, [CHANGE_NOTE])
  await stubAnswer(page, {})
  await load(page, DESKTOP)

  const note = page.locator('.sp-note')
  await expect(note).toBeVisible({ timeout: 15000 })
  await expect(note.locator('.sp-note-title')).toHaveText('Hinder')
  await expect(note.locator('li')).toHaveCount(2)
  // An effect that did nothing says so, in its own voice — the whole point of
  // the splash (a refusal used to look exactly like a success).
  await expect(note.locator('li.is-silent')).toHaveText('no trait instance to move (unset)')
  await expect(page.locator('.sp-prompt')).toHaveCount(0)

  // A report, not a decision: it goes away by itself (1–2 s for a change).
  await expect(page.locator('.sp-note')).toHaveCount(0, { timeout: 4000 })
})

test('a rule that has run its course reports for longer', async ({ page }) => {
  await stubStream(page, null, [SUMMARY_NOTE])
  await stubAnswer(page, {})
  await load(page, DESKTOP)

  await expect(page.locator('.sp-note')).toBeVisible({ timeout: 15000 })
  // 3–5 s: still there past a change's dwell, gone well before a minute.
  await page.waitForTimeout(3000)
  await expect(page.locator('.sp-note')).toBeVisible()
  await expect(page.locator('.sp-note')).toHaveCount(0, { timeout: 4000 })
})

test('a burst of changes queues rather than stacking', async ({ page }) => {
  const second = { ...CHANGE_NOTE, title: 'Spray n Pray', lines: [{ text: 'pool: added d6' }] }
  await stubStream(page, null, [CHANGE_NOTE, second])
  await stubAnswer(page, {})
  await load(page, DESKTOP)

  // One at a time, in order: the second arrives after the first has gone.
  await expect(page.locator('.sp-note')).toHaveCount(1)
  await expect(page.locator('.sp-note-title')).toHaveText('Hinder')
  await expect(page.locator('.sp-note-title')).toHaveText('Spray n Pray', { timeout: 6000 })
  await expect(page.locator('.sp-note')).toHaveCount(1)
})

test('a change to someone else is not mine to read', async ({ page }) => {
  const notMine = { ...CHANGE_NOTE, entity_id: 'character-somebody-else', title: 'Not mine' }
  await stubStream(page, null, [notMine])
  await stubAnswer(page, {})
  await load(page, DESKTOP)

  // Give it the full dwell of a change plus the queue's first turn, then check
  // nothing ever appeared.
  await page.waitForTimeout(3000)
  await expect(page.locator('.sp-note')).toHaveCount(0)
})

test('a note waits rather than fading behind a question', async ({ page }) => {
  // Both at once: the question takes the surface, and the report must not spend
  // its life hidden behind it.
  await stubStream(page, [AUTO_CHOICE], [CHANGE_NOTE])
  await stubAnswer(page, {})
  await load(page, DESKTOP)

  const prompt = page.locator('.sp-prompt')
  await expect(prompt).toBeVisible({ timeout: 15000 })
  await page.waitForTimeout(3000)
  await expect(page.locator('.sp-note'), 'the note is not shown behind the question').toHaveCount(0)

  // Answering the question releases the queue, so the report is finally read.
  await page.locator('.sp-prompt .etw-candidate').first().click()
  await expect(page.locator('.sp-note')).toBeVisible({ timeout: 5000 })
  await expect(page.locator('.sp-note-title')).toHaveText('Hinder')
})

// ── the authored client action ([[B132]]) ───────────────────────────────────
//
// `client_action` goes to every session and names its `recipient_id`; a client
// that is not the recipient ignores it. A **sticky** toast is what the splash is
// for — a message that waits for the player, and may carry an authored action.
//
// The *difficulty target* is the other user of this face and has its own spec
// (`difficulty-target-splash.spec.js`, B287) — it is not duplicated here.

/** A message with something to press: the press is the dismissal. */
const ACTIONABLE_TOAST = {
  action: 'toast', recipient_id: KAEL, target_id: KAEL,
  message: 'The court convenes', sticky: true, tap: 'open_sheet',
}
/** A message with nothing to press, so it needs the ✕. */
const PLAIN_STICKY_TOAST = {
  action: 'toast', recipient_id: KAEL, message: 'The court convenes', sticky: true,
}

test('an authored toast splashes front and centre, and waits for the player', async ({ page }) => {
  await stubStream(page, null, [], [{ type: 'client_action', data: ACTIONABLE_TOAST }])
  await stubAnswer(page, {})
  await load(page, DESKTOP)

  const note = page.locator('.sp-note-action')
  await expect(note).toBeVisible({ timeout: 15000 })
  await expect(note).toContainText('The court convenes')
  await expect(note.locator('.sp-note-cue')).toHaveText('Open character sheet')

  const off = await offCentre(page)
  expect(Math.abs(off.dx), 'centred horizontally').toBeLessThanOrEqual(2)
  expect(Math.abs(off.dy), 'centred vertically').toBeLessThanOrEqual(2)

  // Sticky: a plain report would be long gone by now (a change lands for 1–2 s).
  // Without the stickiness the card would vanish mid-reach — the failure this
  // asserts against.
  await page.waitForTimeout(3500)
  await expect(note).toBeVisible()
})

test('tapping an actionable message opens the sheet and gets out of its way', async ({ page }) => {
  await stubStream(page, null, [], [{ type: 'client_action', data: ACTIONABLE_TOAST }])
  await stubAnswer(page, {})
  // A phone, because that is where "focus the sheet" is visible as an act: the
  // band stack has to expand it. In the docked desktop layout the sheet is
  // permanently up, so there is nothing to watch.
  await load(page, PHONE)
  await expect(page.locator('.stage')).toHaveClass(/focus-location/, { timeout: 15000 })

  // The card *is* the control — a tap anywhere on it does the thing.
  await page.locator('.sp-note-action').click()

  // The band expands…
  await expect(page.locator('.stage')).toHaveClass(/focus-sheet/)
  // …and the card is gone: a front-and-centre message left over the sheet it just
  // opened would hide the point of tapping it.
  await expect(page.locator('.sp-note')).toHaveCount(0)
})

test('a sticky message with nothing to press carries its own way out', async ({ page }) => {
  await stubStream(page, null, [], [{ type: 'client_action', data: PLAIN_STICKY_TOAST }])
  await stubAnswer(page, {})
  await load(page, DESKTOP)

  // No action, so it is a notice rather than a target — and a card that waits for
  // ever with no exit would be a trap.
  const note = page.locator('.sp-note')
  await expect(note).toBeVisible({ timeout: 15000 })
  await expect(page.locator('.sp-note-action')).toHaveCount(0)
  await page.waitForTimeout(3500)
  await expect(note, 'sticky, so it outlives a report').toBeVisible()

  await page.locator('.sp-note-close').click()
  await expect(page.locator('.sp-note')).toHaveCount(0)
})

test('a bare open_sheet action focuses the sheet with no message at all', async ({ page }) => {
  await stubStream(page, null, [], [{
    type: 'client_action',
    data: { action: 'open_sheet', recipient_id: KAEL, target_id: KAEL },
  }])
  await stubAnswer(page, {})
  await load(page, PHONE)

  await expect(page.locator('.stage')).toHaveClass(/focus-sheet/, { timeout: 15000 })
  await expect(page.locator('.sp-root')).toHaveCount(0)
})

test('a non-sticky toast stays the plain toast, not the splash', async ({ page }) => {
  await stubStream(page, null, [], [{
    type: 'client_action',
    data: { action: 'toast', recipient_id: KAEL, message: 'The court convenes' },
  }])
  await stubAnswer(page, {})
  await load(page, DESKTOP)

  await expect(page.locator('.toast-item')).toBeVisible({ timeout: 15000 })
  await expect(page.locator('.sp-root')).toHaveCount(0)
})

test('a client action to somebody else is not mine to act on', async ({ page }) => {
  await stubStream(page, null, [], [{
    type: 'client_action',
    data: { ...ACTIONABLE_TOAST, recipient_id: 'character-somebody-else' },
  }])
  await stubAnswer(page, {})
  await load(page, DESKTOP)

  await page.waitForTimeout(3000)
  await expect(page.locator('.sp-root')).toHaveCount(0)
})
