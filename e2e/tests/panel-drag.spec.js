// The panel drag gestures — the two the human asked for on 2026-10-16:
//
//   "Instead of detaching panels with a dedicated button, it should be
//    detachable by moving the drag handle away from its parent. I'd also like it
//    if dragging a floating panel's drag handle onto the edge of another panel,
//    that it can anchor on it."
//
// Settled with him: dropping onto a panel makes the window **that panel's child**
// (not a tethered float), and the ⠿ handle is the keyboard path to detaching now
// that the button is gone — so Enter on the handle is a real case, not a nicety.
//
// `check-panel-drag.mjs` proves the registry and reads the wiring; whether a
// pointer drag actually tears a panel out and whether a drop lands are *browser*
// facts and are only provable here.
import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { bootGmPanel, enterPrep, detachByDrag } from '../helpers/gm.js'

const TEST_CHARACTER = 'character-kael-drift-e555ccde'
const WINDOWS = '[data-panel-window]:not([data-panel-window="root"])'
const ROOT_PANEL = '[data-panel-window="root"][data-panel-depth="0"]'

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === TEST_CHARACTER && a.main))
  if (!owner) throw new Error(`no player mains ${TEST_CHARACTER} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: TEST_CHARACTER }
})

/** Open the chain and a child panel in it (the location tree's first row). */
async function openAChildPanel(page) {
  await bootGmPanel(page, character)
  await enterPrep(page)
  await page.locator('.tree-row').first().click()
  await page.waitForTimeout(1400)
  await expect(page.locator('[data-panel-depth="1"]:visible'), 'a child panel is open').not.toHaveCount(0)
}

test('the rail no longer offers a detach button', async ({ page }) => {
  await openAChildPanel(page)
  await expect(page.locator('[title="Detach into a floating window"]'),
    'the ⤢ button is gone — the gesture replaces it').toHaveCount(0)
  await expect(page.locator('[data-panel-depth="1"]:visible .panel-drag-handle'),
    'and the handle is still there to do it').toHaveCount(1)
})

test('dragging the handle away from the parent detaches the panel', async ({ page }) => {
  await openAChildPanel(page)
  await expect(page.locator(WINDOWS), 'nothing is floating yet').toHaveCount(0)

  await detachByDrag(page)

  await expect(page.locator(WINDOWS), 'the panel came out as a floating window').toHaveCount(1)
  // Detaching is a *move*: the panel left the chain rather than being copied.
  await expect(page.locator(`${WINDOWS} .panel-title`), 'and it is the panel that was dragged')
    .toContainText(/./)
})

test('Enter on the drag handle detaches — the keyboard path', async ({ page }) => {
  await openAChildPanel(page)
  const handle = page.locator('[data-panel-depth="1"]:visible .panel-drag-handle').first()
  await handle.focus()
  await page.keyboard.press('Enter')
  await page.waitForTimeout(1200)
  await expect(page.locator(WINDOWS), 'the focused handle detached the panel').toHaveCount(1)
})

test('dropping a floating panel on another panel makes it that panel\'s child', async ({ page }) => {
  await openAChildPanel(page)
  await detachByDrag(page)
  await expect(page.locator(WINDOWS), 'a window to drag').toHaveCount(1)

  // Drag the *window's* handle onto the chain root's own box.
  const root = await page.locator(ROOT_PANEL).boundingBox()
  const handle = await page.locator(`${WINDOWS} .panel-drag-handle`).first().boundingBox()
  expect(root && handle, 'both the target and the handle are measurable').toBeTruthy()
  await page.mouse.move(handle.x + handle.width / 2, handle.y + handle.height / 2)
  await page.mouse.down()
  await page.mouse.move(root.x + root.width / 2, root.y + root.height / 2, { steps: 8 })
  // Mid-drag the target lights up, so the drop is not a guess.
  await expect(page.locator(`${ROOT_PANEL}.is-drop-target`), 'the target shows it would take it')
    .toHaveCount(1)
  await page.mouse.up()
  await page.waitForTimeout(1200)

  await expect(page.locator(WINDOWS), 'the window is gone — it is a child now').toHaveCount(0)
  await expect(page.locator('[data-panel-depth="1"]:visible'), 'and it is in the chain').not.toHaveCount(0)
  await expect(page.locator('.is-drop-target'), 'and the highlight is cleared').toHaveCount(0)
})
