// Reaching arrange mode from the e2e harness.
//
// Arrange mode is architect-only, and the role comes from `GET /players/{id}`. So a spec
// gets there by mocking that ONE read to `architect` rather than logging in as one of the
// human's own devices (which are theirs, not the harness's). The route has to be
// registered BEFORE the page loads, because the role is fetched on mount.

/** Make the testing player read as an architect. Call before `page.goto`. */
export async function asArchitect(page) {
  await page.route('**/api/v1/players/*', async (route) => {
    const body = await (await route.fetch()).json()
    return route.fulfill({ json: { ...body, role: 'architect' } })
  })
}

/** Turn arrange mode on. Requires `asArchitect` and a loaded page. */
export async function enterArrangeMode(page) {
  await page.locator('.arrange-btn').click()
}
