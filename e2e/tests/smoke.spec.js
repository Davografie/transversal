import { test, expect } from '@playwright/test'

// Smoke-level verification of the app shell.
//
// These deliberately assert the *shell*, not the game: enough to catch a blank
// page, a broken build, a module that fails to mount, or an unhandled error on
// boot — the failures that otherwise get reported as "it just doesn't load".
//
// The app opens on an identity gate ("Who are you?"), so an unauthenticated
// browser sees that rather than the game. Assertions below assume no session.

test('the app shell mounts without errors', async ({ page }) => {
  const pageErrors = []
  page.on('pageerror', (e) => pageErrors.push(String(e)))

  await page.goto('/')

  await expect(page).toHaveTitle(/Transversal/i)
  await expect(page.locator('#app')).toBeAttached()

  // No session -> the identity prompt is what a fresh browser gets.
  await expect(page.getByText(/who are you\?/i)).toBeVisible()

  expect(pageErrors, `uncaught page errors: ${pageErrors.join(' | ')}`).toEqual([])
})

test('the identity field is interactive', async ({ page }) => {
  await page.goto('/')

  // The name field is the app's first interaction point. Typing proves the
  // interactive shell is alive rather than a static shell that merely rendered.
  const field = page.getByPlaceholder(/your name/i)
  await expect(field).toBeVisible()
  await field.fill('e2e-probe')

  await expect(field).toHaveValue('e2e-probe')
  // Typing searches existing players; the create row appears for an unknown name.
  await expect(page.getByText(/new transverser/i)).toBeVisible()
})
