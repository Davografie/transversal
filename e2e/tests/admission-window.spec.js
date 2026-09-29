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

  // And the window is listed, so the GM can see and close what they opened.
  await expect(page.getByRole('button', { name: /close all windows/i })).toBeVisible()

  // Tidy up: leave no open window behind for the next spec that runs.
  await page.getByRole('button', { name: /close all windows/i }).click()
  await expect(page.getByRole('button', { name: /close all windows/i })).toBeHidden()
})
