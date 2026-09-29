import { test, expect } from '@playwright/test'

import { admitDevice } from '../helpers/session.js'

// Smoke-level verification of the app shell.
//
// These deliberately assert the *shell*, not the game: enough to catch a blank
// page, a broken build, a module that fails to mount, or an unhandled error on
// boot — the failures that otherwise get reported as "it just doesn't load".
//
// SEC-3 changed what an unauthenticated browser sees. There is no in-app login any
// more: a device with no session is refused by the perimeter and shown the sealed
// notice, and a device that has come through a passage link but not yet said who it
// is gets the **roster picker**. Both are asserted, because both are real states a
// person lands in.

test('the app shell mounts without errors', async ({ page }) => {
  const pageErrors = []
  page.on('pageerror', (e) => pageErrors.push(String(e)))

  await page.goto('/')

  await expect(page).toHaveTitle(/Transversal/i)
  await expect(page.locator('#app')).toBeAttached()

  // No session -> the perimeter refused everything, and the app says so rather
  // than rendering a shell that silently does nothing.
  await expect(page.getByText(/the way is sealed/i)).toBeVisible()

  expect(pageErrors, `uncaught page errors: ${pageErrors.join(' | ')}`).toEqual([])
})

test('an admitted device is asked who it is, and can answer', async ({ page }) => {
  await admitDevice(page)
  await page.goto('/')

  // The picker is the app's first interaction point now (SEC-3): a list of who is
  // at the table, plus a field for someone new. Typing proves the shell is alive
  // rather than merely rendered.
  const field = page.getByPlaceholder(/or a new name/i)
  await expect(field).toBeVisible()
  await field.fill('e2e-probe')

  await expect(field).toHaveValue('e2e-probe')
  await expect(page.getByRole('button', { name: /begin/i })).toBeEnabled()
})
