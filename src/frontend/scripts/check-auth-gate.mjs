/**
 * Executable check for the access-perimeter notice.
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-auth-gate.mjs
 *
 * The report: approaching the app without a valid token or cookie left the app
 * silently empty — the login screen's name search offered no suggestions and
 * nothing said why. In a deployed build nginx gates every `/api/` request with
 * `auth_request`, answering **401 with an HTML error page**; the app's ~78 call
 * sites `await r.json()` and swallow the parse error, so the cause is invisible.
 *
 * `useAuthGate` notices the 401 once, where every request passes. This checks the
 * noticing, its stickiness, and that it is actually installed and rendered — a gate
 * nothing installs, or a notice nothing renders, would look exactly like the bug.
 */
import { readFileSync } from 'node:fs'
import { installAuthGate, unauthorized } from '../src/composables/useAuthGate.js'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}

// ── 1. it notices a 401, and only that ──────────────────────────────────
console.log('\nauth gate — the perimeter answers 401\n')

const calls = []
let nextStatus = 200
globalThis.window = {
  async fetch(...args) { calls.push(args); return { status: nextStatus } },
}
const native = globalThis.window.fetch

installAuthGate()
ok('the gate takes over window.fetch', globalThis.window.fetch === native, false)

nextStatus = 401
const refused = await window.fetch('/api/v1/players?q=ann')
ok('a 401 raises the notice', unauthorized.value, true)
ok('…and the response still reaches the caller', refused.status, 401)

unauthorized.value = false
nextStatus = 200
const served = await window.fetch('/api/v1/graphql', { method: 'POST' })
ok('a 200 leaves it alone', unauthorized.value, false)
ok('…and is passed through untouched', served.status, 200)
ok('arguments are forwarded verbatim', calls.at(-1)[0], '/api/v1/graphql')

// ── 2. stickiness and idempotence ───────────────────────────────────────
console.log('\nauth gate — sticky, and installed once\n')

nextStatus = 401
await window.fetch('/api/v1/players')
nextStatus = 200
await window.fetch('/api/v1/players')
ok('once raised it stays raised (a page cannot re-key itself)', unauthorized.value, true)

const installedOnce = globalThis.window.fetch
installAuthGate()
ok('installing again does not wrap it twice', globalThis.window.fetch, installedOnce)

unauthorized.value = false
const before = calls.length
nextStatus = 401
await window.fetch('/api/v1/entities')
ok('one call reaches the network once', calls.length - before, 1)
ok('…and still raises the notice', unauthorized.value, true)

{
  // The symptom, for contrast: without the gate the same 401 raises nothing.
  unauthorized.value = false
  await (async () => ({ status: 401 }))()
  ok('a bare 401 raises nothing — the silent app that was reported', unauthorized.value, false)
}

// ── 3. it is wired in ───────────────────────────────────────────────────
console.log('\nauth gate — wired in\n')

{
  const main = readFileSync('src/main.js', 'utf8')
  ok('main.js installs the gate', main.includes('installAuthGate()'), true)
  ok('…before mounting, so the first request is watched',
    main.indexOf('installAuthGate()') < main.indexOf('createApp(App).mount'), true)

  const app = readFileSync('src/App.vue', 'utf8')
  ok('App.vue imports the notice',
    /import UnauthorizedNotice from '@\/components\/app\/UnauthorizedNotice\.vue'/.test(app), true)
  ok('App.vue renders it while unauthorized',
    /<UnauthorizedNotice v-if="unauthorized"\s*\/>/.test(app), true)

  // The copy must not teach the token route. The magic link is the only thing that
  // carries `t=`, and the QR that encodes it is not shown in the app — naming the
  // shape of the perimeter here would hand it to exactly the audience that reached
  // the app *without* a token. Checked against the rendered template only, so a
  // source comment may still explain the mechanism to the next reader.
  const noticeSource = readFileSync('src/components/app/UnauthorizedNotice.vue', 'utf8')
  const renderedCopy = (noticeSource.match(/<template>([\s\S]*?)<\/template>/) || [, ''])[1]
    .replace(/<!--[\s\S]*?-->/g, '')
  ok('the notice copy does not name the token route',
    /\/enter\b|access_token|\bt=|token=/i.test(renderedCopy), false)
}

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
