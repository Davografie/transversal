import { ref } from 'vue'

/**
 * The access perimeter, as the app experiences it.
 *
 * In a deployed build every `/api/` and `/media/` request passes through nginx's
 * `auth_request /_auth` gate, which answers **401** — with an HTML error page, not
 * JSON — when the session cookie is missing or has expired. The app's ~78 call
 * sites mostly `await r.json()` and swallow the throw, so a rejected request turns
 * into silence: the app loads, then quietly does nothing. That is the reported
 * symptom — the login screen's name search simply offers no suggestions, with no
 * hint that the archive refused every request.
 *
 * So the perimeter is noticed once, at the single place every request goes
 * through. Patching `fetch` rather than threading a wrapper through 78 call sites:
 * a process-wide condition has one chokepoint, and a wrapper would have to reach
 * every composable and component to be as complete.
 *
 * Only `auth.py` answers 401 in the API, and the app calls neither of its routes
 * (`/enter` is a top-level navigation, `/check` is nginx's), so a 401 here can
 * only be the perimeter.
 */
export const unauthorized = ref(false)

let installed = false

export function installAuthGate() {
  if (installed) return
  installed = true
  const nativeFetch = window.fetch.bind(window)
  window.fetch = async (...args) => {
    const response = await nativeFetch(...args)
    if (response.status === 401 && !unauthorized.value) {
      unauthorized.value = true
      console.warn(
        '[auth] the perimeter refused a request (401) — no valid passage token; '
        + 'showing the sealed-crossing notice',
      )
    }
    return response
  }
}
