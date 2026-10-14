// Fullscreen: the setting, the device memory, and the manners.
//
// The app shell is `html, body, #app { overflow: hidden }` with every scroll
// inside a band or a panel, so the document never scrolls — and a browser only
// retracts its address bar on a document scroll. On a phone the bar is therefore
// permanent chrome over the play surface. `100dvh` keeps the layout honest about
// the space left; fullscreen is what reclaims it ([[UI-UX Design#Fullscreen]]).
//
// What is asserted here is the part that *behaves*, not the layout:
//
//   * the control is the last thing on the settings screen, and the default is
//     Off — nobody is put into fullscreen before asking for it;
//   * choosing On enters real fullscreen (a genuine trusted click, so the
//     request has the transient activation a browser requires);
//   * a **user** exit is respected — the player left with the back gesture to
//     reach another tab, so the next clicks must not take it straight back;
//   * leaving the page and returning re-arms it, and so does tapping the
//     setting again (the selection never changed, which is why the control opts
//     into `reselect`);
//   * the choice is remembered per device, and so is the kind of device — a
//     real touch is what makes `Auto` fire, so a synthetic mouse click on the
//     same screen must *not*.
//
// SEC-3: identity is a server session now, so the spec enters as the architect
// and takes the testing player (`helpers/gm.js`'s path); `ARCHITECT_TOKEN` must
// be in the environment.
import { test, expect, devices } from '@playwright/test'
import { findPlayableCharacter } from '../helpers/sheet.js'
import { asArchitect } from '../helpers/arrange.js'
import { establishSession } from '../helpers/session.js'

let character
test.beforeAll(async ({ request }) => {
  character = await findPlayableCharacter(request)
})

/**
 * Seed the testing identity, obtain a session, and load the app in GM mode —
 * which is where the settings screen's own button lives (the fixed ↩).
 */
async function boot(page) {
  await asArchitect(page)
  await page.addInitScript(([pid, pname, eid]) => {
    localStorage.setItem('playerId', pid)
    localStorage.setItem('playerName', pname)
    localStorage.setItem('entityId', eid)
    localStorage.setItem('architectMode', 'true')
  }, [character.playerId, character.playerName, character.entityId])
  await page.goto('/')
  await establishSession(page)
  await page.goto('/')
  await page.waitForTimeout(2500)
  await page.locator('.settings-btn').click()
  await page.locator('.name-entry').waitFor({ state: 'visible', timeout: 20000 })
}

const section = (page) =>
  page.locator('.settings-section').filter({
    has: page.locator('.settings-label', { hasText: /^Fullscreen$/ }),
  })

const note = (page) => section(page).locator('.settings-note')

// This suite drives `asArchitect`'s route, and the app keeps polling after the
// test ends — a route callback that fires then fails the test. Same fix as the
// palette and splash specs.
test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' })
})

/** Leave the page and come back — the thing that re-arms `auto`.
 *
 * `visibilityState` is read-only in a real document, so it is overridden to
 * drive the handler. What matters is that the *app's* state is then waited on
 * (the note changes) rather than assumed: the first cut clicked straight after
 * dispatching and failed intermittently, because nothing forced the click to
 * wait for the re-arm it depended on.
 */
async function leaveAndReturn(page) {
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { get: () => 'hidden', configurable: true })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  // While hidden it must *not* re-arm — that is the whole point of the guard.
  await expect(note(page)).toContainText(/Left fullscreen/i)
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { get: () => 'visible', configurable: true })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  await expect(note(page)).toContainText(/Always fullscreen|Touch screen detected|Mouse or keyboard/i)
}

const segment = (page, label) => section(page).locator('.segmented-btn', { hasText: new RegExp(`^${label}$`) })

const state = (page) =>
  page.evaluate(() => ({
    fullscreen: !!document.fullscreenElement,
    mode: localStorage.getItem('fullscreenMode'),
    kind: localStorage.getItem('inputKind'),
  }))

/** What the back gesture does: the browser leaves without asking us. */
const userExit = (page) => page.evaluate(() => document.exitFullscreen())

test('the control is the last thing on the settings screen, off by default', async ({ page }) => {
  await boot(page)

  // The screen's order, asserted as order rather than as a screenshot: Mode is
  // what the app *is*, then the characters you came for, then how this device
  // shows the game — set once, so it must not sit in the way.
  const labels = await page.evaluate(() =>
    [...document.querySelectorAll('.name-entry .settings-label')].map((e) => e.textContent.trim()),
  )
  expect(labels.slice(-3)).toEqual(['Appearance', 'Media quality', 'Fullscreen'])
  expect(labels.indexOf('Find character')).toBeLessThan(labels.indexOf('Appearance'))
  expect(labels.indexOf('Mode')).toBeLessThan(labels.indexOf('Your characters'))

  await expect(section(page)).toHaveCount(1)
  expect(await section(page).locator('.segmented-btn').allInnerTexts()).toEqual(['Off', 'On', 'Auto'])
  // A device that has never been asked starts out of the way.
  await expect(segment(page, 'Off')).toHaveClass(/active/)
  expect((await state(page)).mode).toBeNull()

  // A browser that cannot do it says so instead of offering a dead switch.
  const supported = await page.evaluate(() => document.fullscreenEnabled === true)
  const disabled = await section(page)
    .locator('.segmented-btn')
    .evaluateAll((els) => els.map((e) => e.disabled))
  expect(disabled).toEqual([false, !supported, !supported])
  if (!supported) {
    await expect(section(page).locator('.settings-note')).toContainText(/Home Screen/i)
  }
})

test('On enters, a user exit is respected, and asking again resumes', async ({ page }) => {
  await boot(page)
  await expect(segment(page, 'Off')).toHaveClass(/active/)

  // The click is the gesture the browser requires — no stub, real fullscreen.
  await segment(page, 'On').click()
  await expect.poll(async () => (await state(page)).fullscreen).toBe(true)
  expect((await state(page)).mode).toBe('on')

  // The player leaves with the back gesture.
  await userExit(page)
  await expect.poll(async () => (await state(page)).fullscreen).toBe(false)

  // …and is not taken straight back into it.
  await page.locator('.name-entry .settings-label').first().click()
  await page.waitForTimeout(300)
  await page.locator('.name-entry .settings-label').first().click()
  await page.waitForTimeout(500)
  expect((await state(page)).fullscreen, 'clicking elsewhere must not re-take fullscreen').toBe(false)
  await expect(section(page).locator('.settings-note')).toContainText(/Left fullscreen/i)

  // The way back in is the setting itself: the selection never changed, so this
  // is the `reselect` path and not a second choice.
  await segment(page, 'On').click()
  await expect.poll(async () => (await state(page)).fullscreen).toBe(true)

  // Leaving the page and returning re-arms it too.
  await userExit(page)
  await expect.poll(async () => (await state(page)).fullscreen).toBe(false)
  await leaveAndReturn(page)
  await page.locator('.name-entry .settings-label').first().click()
  await expect.poll(async () => (await state(page)).fullscreen).toBe(true)
})

test('the choice is remembered per device, and Off is the only thing that leaves', async ({ page }) => {
  await boot(page)
  await segment(page, 'On').click()
  await expect.poll(async () => (await state(page)).fullscreen).toBe(true)
  await segment(page, 'Off').click()
  await expect.poll(async () => (await state(page)).fullscreen).toBe(false)
  expect((await state(page)).mode).toBe('off')

  await segment(page, 'Auto').click()
  await page.reload()
  await page.waitForTimeout(2500)
  await page.locator('.settings-btn').click()
  await page.locator('.name-entry').waitFor({ state: 'visible', timeout: 20000 })

  // A reload cannot enter by itself (no gesture), but the choice is still there
  // and the next click takes it.
  expect((await state(page)).mode).toBe('auto')
  await expect(segment(page, 'Auto')).toHaveClass(/active/)
  if (await page.evaluate(() => document.fullscreenEnabled === true)) {
    const coarse = await page.evaluate(() =>
      window.matchMedia('(hover: none) and (pointer: coarse)').matches,
    )
    await page.locator('.name-entry .settings-label').first().click()
    await page.waitForTimeout(600)
    // Whether that click entered depends on the device kind — which is the point
    // of the next case, so here only the *decision* is asserted.
    expect((await state(page)).fullscreen).toBe(coarse)
  }
})

test('a touch screen is remembered, and Auto is what acts on it', async ({ browser, browserName }) => {
  // Chromium's touch emulation reports `pointerType` faithfully; Firefox's does
  // not (maxTouchPoints stays 0 and the synthetic-mouse pointerdown is late), so
  // the device bookkeeping is only checkable in one engine. The behaviour it
  // guards — Auto entering on a tap — is asserted below in both.
  test.skip(browserName !== 'chromium', 'Firefox touch emulation does not report pointerType')

  const context = await browser.newContext({ ...devices['Pixel 7'] })
  const page = await context.newPage()
  await boot(page)

  expect(await page.evaluate(() => window.matchMedia('(hover: none) and (pointer: coarse)').matches)).toBe(true)
  // A synthetic mouse click is a mouse: on a touch-capable laptop this is what
  // stops Auto from firing, and it must record that.
  await page.locator('.name-entry .settings-label').first().click()
  expect((await state(page)).kind).toBe('pointer')

  // A real tap is a touch, and Auto enters on it.
  const box = await segment(page, 'Auto').boundingBox()
  await page.touchscreen.tap(box.x + box.width / 2, box.y + box.height / 2)
  await expect.poll(async () => (await state(page)).fullscreen).toBe(true)
  expect((await state(page)).kind).toBe('touch')
  expect((await state(page)).mode).toBe('auto')
  await expect(section(page).locator('.settings-note')).toContainText(/Touch screen detected/i)

  await context.close()
})
