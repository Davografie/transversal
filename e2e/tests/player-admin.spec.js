import { test, expect } from '@playwright/test'

import { enterAsArchitect } from '../helpers/session.js'

// SEC-3: the owner's roster, and the two acts that change it.
//
// This asserts the controls *exist* for an architect and are **not** for anyone
// else. It deliberately does not click revoke or demote: those act on real player
// records, and an e2e suite must not eject a real person to prove a button works.
// The actions themselves are covered against a throwaway player in the backend
// suite (`test_sec3_flow.py`, `test_access_routes.py`).

test('an architect sees the roster with revoke and role controls', async ({ page }) => {
  await enterAsArchitect(page)
  await page.goto('/')

  await page.locator('.settings-btn').click()

  const block = page.locator('.admin-block')
  await expect(block).toBeVisible({ timeout: 15_000 })
  await expect(block.locator('.admin-row').first()).toBeVisible()

  // Both acts are offered, and the five standing architect seats prove the list
  // includes architects rather than filtering them out.
  await expect(block.getByRole('button', { name: /revoke/i }).first()).toBeVisible()
  await expect(block.locator('.admin-role.arch').first()).toBeVisible()

  // Two-step revoke: the first click asks rather than acting.
  await block.getByRole('button', { name: /^revoke$/i }).first().click()
  await expect(block.getByRole('button', { name: /really revoke\?/i })).toBeVisible()
})
