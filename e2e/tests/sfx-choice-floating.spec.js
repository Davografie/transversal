// B230 — the floating host for an **automatic** rule's question.
//
// The routing rule is the author's: a manual press asks on the sheet, a roll asks
// in the roller, and an automatic rule — a state change or a timer nobody pressed
// — asks in a floating panel, because there is no obvious place its reader is
// looking. The server tags every choice with `origin`; the shell routes by it.
//
// What only a browser can show is the *host*, and each of its failure modes is
// quiet: the question falling through to the roller (where a reader who is not
// rolling will never look), a panel that dims or blocks the table it is asking
// about, one that dismisses itself before it is read, or an answer that loses its
// origin so the follow-up lands somewhere else. So this spec raises a real
// `sfx_choice_required` event with `origin: 'auto'` over the SSE connection and
// measures the result.
//
// The event is served as a canned SSE body rather than by firing a rule: the
// automatic path needs authored content and a real state change, and this spec is
// about where the question renders. Writing is stubbed and every write is
// asserted on, so a run answers nothing.

import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { asPlayer } from '../helpers/role.js'

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
 * Serve one `sfx_choice_required` frame over SSE, then keep the stream quiet on
 * every reconnect (the browser retries when a fulfilled body ends, and re-serving
 * the event would resurrect a question the test has already left behind).
 */
async function stubStream(page, choices = [AUTO_CHOICE]) {
  let served = false
  await page.route('**/api/v1/stream*', async (route) => {
    const headers = { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' }
    if (served) return route.fulfill({ status: 200, headers, body: ': idle\n\n' })
    served = true
    const frame = `event: sfx_choice_required\ndata: ${JSON.stringify({ entity_id: KAEL, choices })}\n\n`
    return route.fulfill({ status: 200, headers, body: frame })
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
  await page.goto('/')
  await page.locator('.name-entry.panel').first().waitFor({ state: 'hidden', timeout: 20000 })
}

const boxOf = (page, sel) => page.evaluate((s) => {
  const el = document.querySelector(s)
  if (!el) return null
  const b = el.getBoundingClientRect()
  return { x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height), right: Math.round(b.right), bottom: Math.round(b.bottom) }
}, sel)

test('an automatic rule asks in a floating panel, and the roller does not show it', async ({ page }) => {
  const problems = watch(page)
  const extras = {}
  await stubStream(page)
  await stubAnswer(page, extras)
  await load(page, DESKTOP)

  const panel = page.locator('.fcp-root')
  await expect(panel).toBeVisible({ timeout: 15000 })
  // The wizard is the content; the host only positions it.
  await expect(panel.locator('.etw-root')).toBeVisible()
  await expect(panel.locator('.etw-title')).toHaveText('A rule needs a choice')
  // …and it is *only* here: `origin: auto` must not fall through to the roller,
  // whose reader is looking at a pool, not at a question about the world.
  await expect(page.locator('.sfx-choice-panel')).toHaveCount(0)

  // Not modal: no dimming, nothing blocked. The sheet stays readable behind it,
  // and the map is still the hit target outside the panel's own box.
  const geometry = await page.evaluate(() => {
    const fcp = document.querySelector('.fcp-root').getBoundingClientRect()
    const cx = Math.round(window.innerWidth / 2)
    const cy = Math.round(window.innerHeight / 2)
    const atCentre = document.elementFromPoint(cx, cy)
    return {
      areaShare: (fcp.width * fcp.height) / (window.innerWidth * window.innerHeight),
      centreIsPanel: !!atCentre?.closest('.fcp-root'),
      sheetVisible: !!document.querySelector('.sheet-embedded')?.offsetParent,
    }
  })
  expect(geometry.centreIsPanel, 'the panel does not cover the middle of the table').toBe(false)
  expect(geometry.areaShare, 'a corner card, not a full-screen dialog').toBeLessThan(0.35)
  expect(geometry.sheetVisible, 'the sheet stays readable behind the question').toBe(true)

  // Desktop corner: bottom-right, clear of the dock (left) and the roller (bottom-centre).
  const b = await boxOf(page, '.fcp-root')
  expect(Math.abs(b.right - DESKTOP.width)).toBeLessThanOrEqual(20)
  expect(Math.abs(b.bottom - DESKTOP.height)).toBeLessThanOrEqual(20)
})

test('it never answers itself, and leaving it writes nothing', async ({ page }) => {
  const problems = watch(page)
  const extras = {}
  await stubStream(page)
  await stubAnswer(page, extras)
  await load(page, DESKTOP)

  await expect(page.locator('.fcp-root')).toBeVisible({ timeout: 15000 })
  // No timer: a question nobody asked for waits to be read. If a dismissal timer
  // ever creeps in, this is the assertion that catches it.
  await page.waitForTimeout(2500)
  await expect(page.locator('.fcp-root')).toBeVisible()

  await page.locator('.fcp-root .etw-cancel').click()
  await expect(page.locator('.fcp-root')).toHaveCount(0)
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

  await expect(page.locator('.fcp-root')).toBeVisible({ timeout: 15000 })
  // A single-choice step commits on the pick — the click *is* the answer.
  await page.locator('.fcp-root .etw-candidate').first().click()
  await expect(page.locator('.fcp-root')).toHaveCount(0)

  await expect.poll(() => extras.answered?.origin).toBe('auto')
  expect(extras.answered?.resolutions?.[0]?.answers?.[0]?.ids).toEqual(['trait-e2e-a'])
  expect(extras.answered?.entityId).toBe(KAEL)
  expect(problems, problems.join('\n')).toEqual([])
})

test('on a phone it takes the top, whole and inside the viewport', async ({ page }) => {
  const problems = watch(page)
  const extras = {}
  await stubStream(page)
  await stubAnswer(page, extras)
  await load(page, PHONE)

  const panel = page.locator('.fcp-root')
  await expect(panel).toBeVisible({ timeout: 15000 })
  await expect(page.locator('.sfx-choice-panel')).toHaveCount(0)

  // The band stack owns the bottom of a phone, so the question takes the top and
  // spans the width — a banner rather than a corner card.
  const b = await boxOf(page, '.fcp-root')
  expect(b.y, 'it starts at the top').toBeLessThan(60)
  expect(b.bottom, 'and fits on screen').toBeLessThanOrEqual(PHONE.height)
  expect(b.w, 'spanning the width').toBeGreaterThan(PHONE.width - 40)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow, 'no horizontal overflow').toBeLessThanOrEqual(0)
})
