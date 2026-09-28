// Reaching arrange mode / the GM panel stack from the e2e harness.
//
// Arrange mode is architect-only, and the role comes from `GET /players/{id}`. So a spec
// gets there by mocking that ONE read to `architect` rather than logging in as one of the
// human's own devices (which are theirs, not the harness's). The route has to be
// registered BEFORE the page loads, because the role is fetched on mount.
//
// ⚠ **The write has to be swallowed too.** `watch(gmMode)` PATCHes the role back to the
// server, so a spec that mocked only the read left `DSH MCP` stored as `architect` — which
// then broke every later run for every session (a GM's own sheet renders no settings
// button, and the whole layout changes). The glob also matters: `*` stops at `/`, so
// `**/api/v1/players/*` never matched `…/players/{id}/role` at all. This mirrors
// `role.js`'s `asPlayer`, which had the same two lessons.

const ROLE_READ = /\/api\/v1\/players\/[^/]+$/

/** Make the testing player read as an architect. Call before `page.goto`. */
export async function asArchitect(page) {
  await page.route('**/api/v1/players/**', async (route) => {
    const req = route.request()
    if (req.method() === 'GET' && ROLE_READ.test(new URL(req.url()).pathname)) {
      const body = await (await route.fetch()).json().catch(() => null)
      return route.fulfill({ json: { ...(body || {}), role: 'architect' } })
    }
    // The app's own write-back, answered locally and never forwarded.
    if (req.url().endsWith('/role')) return route.fulfill({ json: { status: 'ok' } })
    return route.continue()
  })
}

/** Turn arrange mode on. Requires `asArchitect` and a loaded page. */
export async function enterArrangeMode(page) {
  await page.locator('.arrange-btn').click()
}
