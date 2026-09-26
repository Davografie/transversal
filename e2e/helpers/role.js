// Pin the logged-in player's role to `player` for a spec that drives a *player's* sheet.
//
// The app reads the role from `GET /api/v1/players/{id}` and turns `architect` into GM
// free-roam, which sets `entityId = null` (App.vue's `returnToSelf`). An architect's own
// embedded sheet then has no entity, so anything bound to `entityId` — the Blue Book
// above all — renders empty however much history the character has.
//
// That is not a hypothetical: the shared test identity (`DSH MCP`) has been flipped to
// `architect` more than once, and the flip persists because `watch(gmMode)` PATCHes the
// role back to the server. A spec that wants a player's sheet must therefore pin the
// role in the browser rather than depend on shared server state.
//
// The glob matters: `*` stops at `/`, so `**` is required to swallow the `…/role` write
// as well as the read. Swallowing only the read lets the app's own PATCH reach the real
// server and rewrite the fixture — the trap recorded in ui-ux's session doc.
export async function asPlayer(page) {
  await page.route('**/api/v1/players/**', async (route) => {
    const req = route.request()
    if (req.method() === 'GET') {
      const body = await (await route.fetch()).json().catch(() => null)
      if (body && typeof body === 'object' && 'role' in body) body.role = 'player'
      return route.fulfill({ json: body })
    }
    if (req.url().endsWith('/role')) return route.fulfill({ json: { status: 'ok' } })
    return route.continue()
  })
}
