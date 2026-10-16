// Assuming a character from a floating panel.
//
// The report: *"I can assume it through the root GM panel… but not through a
// floating panel that's been loaded through persistence"*, and then, with the
// panel open: *"props.entityId and props.currentEntityId [are both]
// character-20809. Why is props.currentEntityId set to that value? It's just
// incorrect. I'm a roaming GM at the moment."*
//
// He was right, and here is the whole mechanism. Exactly one line writes that
// prop — `GmPanel.openEntityEdit` copies **its own `entityId` prop** into the
// child spec — so a `GmEntityEditPanel` carries the perspective **as it was when
// the panel was opened**. A float keeps the copy it was spawned with (detaching
// copies the spec) and a restored float keeps the copy written to
// `localStorage`, so the copy can be days old. The Assume button is then gated on
// it, and it is wrong in both directions: hidden while you are *not* acting as
// that character (the reported case, when the panel happened to be opened while
// you were), and offered while you *are*.
//
// The panel already injects the live value (`actingEntityId`, App's provide) — it
// is used seven times in the same file and the sibling *Import to Location*
// button reads the live location the same way. Only the Assume gate read the
// snapshot.
import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { asArchitect } from '../helpers/arrange.js'
import { establishSession } from '../helpers/session.js'
import { openStack, enterPrep, detachByDrag } from '../helpers/gm.js'

const KAEL = 'character-kael-drift-e555ccde'
const STORE = 'gmPanelWindows'

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: KAEL }
})

test('a floating entity panel assumes by the live perspective, not its own snapshot', async ({ page }) => {
  const control = []
  page.on('request', (r) => { if (/\/control\//.test(r.url())) control.push(r.method()) })

  await asArchitect(page)
  await page.addInitScript(([pid, pname]) => {
    localStorage.setItem('playerId', pid)
    localStorage.setItem('playerName', pname)
    localStorage.setItem('architectMode', 'true')
  }, [character.playerId, character.playerName])
  await page.goto('/')
  await establishSession(page)
  // Once — NOT in addInitScript, which re-runs on the reload this test needs.
  await page.evaluate(() => { localStorage.removeItem('entityId'); localStorage.removeItem('gmPanelWindows') })
  await page.goto('/')
  await page.waitForTimeout(2500)
  await openStack(page)
  await enterPrep(page)

  const acting = () => page.evaluate(() => localStorage.getItem('entityId'))
  const stored = () => page.evaluate((k) => JSON.parse(localStorage.getItem(k) || '[]'), STORE)
  const openPanel = async () => {
    await page.locator('.filter-input:visible').first().fill('Kael Drift')
    await page.waitForTimeout(900)
    await page.locator('.suggestion-row:visible').first().click()
    await page.waitForTimeout(1800)
  }
  const chainAssume = page.locator('[data-panel-depth="1"]:visible .assume-btn')

  // Act as her, then open her panel *while acting as her* — the state the report
  // was written from (both props the same).
  await openPanel()
  await chainAssume.first().click()
  await page.waitForTimeout(1500)
  expect(await acting(), 'the root panel assumed her').toBe(KAEL)
  await page.locator('[data-panel-depth="1"]:visible [title="Close"]').last().click()
  await page.waitForTimeout(1000)
  await openPanel()

  // Detach it, so the snapshot is written where persistence will keep it.
  await detachByDrag(page)
  await page.waitForTimeout(1200)
  const record = (await stored())[0]
  expect(record, 'the panel is a window now').toBeTruthy()
  expect([record.props.entityId, record.props.currentEntityId],
    'the stored props carry the perspective frozen at open time') .toEqual([KAEL, KAEL])

  // Reload: the float comes back from persistence, and the app is still acting as
  // her (that is persisted per device too).
  await page.reload()
  await page.waitForTimeout(3000)
  expect(await acting(), 'the perspective survived the reload').toBe(KAEL)

  // Now roam again, with the panel still open — the reported situation.
  await page.evaluate(() => document.querySelector('.peer-chip.assumed')?.click())
  await page.waitForTimeout(1500)
  expect(await acting(), 'the GM is roaming again').toBeNull()

  const floatAssume = page.locator('[data-panel-unit]:not([data-panel-unit="root"]):visible .assume-btn')
  await expect(floatAssume, 'the float offers Assume for the character it shows').toHaveCount(1, { timeout: 5000 })

  // And it works, from the float, while roaming.
  control.length = 0
  await floatAssume.first().click()
  await page.waitForTimeout(1500)
  expect(await acting(), 'assuming from the float works').toBe(KAEL)
  expect(control.length, 'and it went through the app (presence control POST)').toBeGreaterThan(0)

  // Leave the test player roaming, not acting as anyone.
  await page.evaluate(() => document.querySelector('.peer-chip.assumed')?.click())
  await page.waitForTimeout(800)
})
