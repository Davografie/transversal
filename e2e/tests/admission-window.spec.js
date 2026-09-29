import { test, expect } from '@playwright/test'

import { gql } from '../helpers/sheet.js'
import { bootGmPanel } from '../helpers/gm.js'

// SEC-3 admission: the GM's window onto the table's front door.
//
// The API half is covered by the backend suite; what a browser has to prove is
// that the block is reachable and that the link it shows is the one that admits.
// The token is minted for real, so this also catches the endpoint and the UI
// drifting apart.

const TEST_CHARACTER = 'character-kael-drift-e555ccde'

let character

test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) =>
    (p.agency || []).some((a) => a.entityId === TEST_CHARACTER && a.main),
  )
  if (!owner) throw new Error(`no player mains ${TEST_CHARACTER} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: TEST_CHARACTER }
})

test('a GM can open an admission window and is shown the link', async ({ page, request }) => {
  await bootGmPanel(page, character)

  await page.locator('.settings-btn').click()
  await expect(page.getByRole('button', { name: /admit players/i })).toBeVisible()

  await page.getByRole('button', { name: /admit players/i }).click()

  // The link that admits, on this origin, carrying a real token.
  const field = page.locator('.admit-link input')
  await expect(field).toBeVisible({ timeout: 10_000 })
  const url = await field.inputValue()
  expect(url).toMatch(/\/enter\?s=.+/)

  // The QR is the point of the ritual: one screen the table can scan. Asserted as
  // a locally-generated data URL — it must never be fetched from a third-party
  // image service, which would hand the admission token to someone else.
  const qr = page.locator('img.admit-qr')
  await expect(qr).toBeVisible()
  expect(await qr.getAttribute('src')).toMatch(/^data:image\/png;base64,/)

  // The window is listed, so whoever opened it can see it and close it. The test
  // identity is a *member*, so close-all (architect-only server-side) must not be
  // offered — asserting that is the point of the next line, and it is why this
  // closes the window directly instead.
  await expect(page.getByRole('button', { name: /close all windows/i })).toBeHidden()
  const rows = page.locator('.char-item', { hasText: 'close' })
  const before = await rows.count()
  expect(before).toBeGreaterThan(0)
  await rows.first().click()
  // One fewer than before, not zero: other windows may be open (a previous run
  // that failed mid-way leaves its own behind), and this spec closes *its* window
  // rather than everyone's — close-all is architect-only and this identity is not.
  await expect(rows).toHaveCount(before - 1)
})
