// Establish a real session for the e2e suite (SEC-3).
//
// The suite used to log in by writing `localStorage.playerId` and reloading. That
// is exactly the client-asserted identity SEC-3 removed: the app no longer reads
// it, and identity now comes from a server-issued session cookie. So a spec has to
// *obtain* a session, not assert one.
//
// How, without a backdoor and without a token per spec:
//
//   1. `/api/v1/auth/enter?a=<ARCHITECT_TOKEN>` — the architect's own way in. It
//      is the one seat never issued from the UI, which is what makes it usable
//      from a machine.
//   2. `POST /api/v1/auth/take/<playerId>` — rebind that session to the player the
//      spec actually wants (the project's testing player). Taking an existing
//      player is a normal, allowed act; architect accounts are the only ones
//      refused.
//
// The API is addressed directly rather than through `/enter` on the app's origin,
// because the dev server only proxies `/api` and `/media` — `/enter` is an nginx
// location (see src/frontend/nginx.conf). Cookies are scoped to the *host*, not
// the port, so a cookie set from :8085 is sent to :3000.
//
// `page.request` shares the browser context's cookie jar, so the session lands in
// the page the spec is about to load.
//
// ARCHITECT_TOKEN must be in the environment running Playwright. It is the same
// value as the API container's; see `.env`.

const API_BASE = process.env.E2E_API_BASE || 'http://localhost:8085'

/**
 * Give `page` a real session bound to the player seeded in `localStorage`.
 *
 * Reads the player the spec already seeded rather than taking an argument, so
 * callers do not have to thread an extra value through: the specs compute
 * `playerId` and write it to storage, and that is exactly the intent to honour.
 */
export async function establishSession(page) {
  const playerId = await page.evaluate(() => localStorage.getItem('playerId'))
  if (!playerId) {
    throw new Error(
      'establishSession: localStorage.playerId was not seeded before the call — ' +
      'the spec must say which player it wants to be.',
    )
  }

  const key = process.env.ARCHITECT_TOKEN
  if (!key) {
    throw new Error(
      'ARCHITECT_TOKEN is not set for the Playwright run. SEC-3 issues sessions ' +
      'from the server, so the suite needs the architect key to obtain one — it is ' +
      'the only way in that is not issued through the UI. Set it in the environment ' +
      '(same value as .env) before running the suite.',
    )
  }

  const entered = await page.request.get(`${API_BASE}/api/v1/auth/enter`, {
    params: { a: key },
  })
  if (!entered.ok() && entered.status() !== 302) {
    throw new Error(`architect entry failed: HTTP ${entered.status()}`)
  }

  const taken = await page.request.post(`${API_BASE}/api/v1/auth/take/${playerId}`)
  if (!taken.ok()) {
    throw new Error(
      `could not take ${playerId}: HTTP ${taken.status()} ${await taken.text()}`,
    )
  }

  const who = await page.request.get(`${API_BASE}/api/v1/auth/session`)
  const body = await who.json()
  if (body?.player?.id !== playerId) {
    throw new Error(
      `session did not bind to ${playerId} (got ${body?.player?.id ?? 'nobody'}) — ` +
      'refusing to run the spec as the wrong identity.',
    )
  }
}
