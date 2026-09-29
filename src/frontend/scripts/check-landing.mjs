/**
 * Executable check for "where you land": the login → character-select hand-off,
 * and the scene load that must follow a perspective change.
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-landing.mjs
 *
 * What it pins, in two halves:
 *
 *  1. **Arriving gives you a name, and taking one loads what follows.** SEC-3 moved
 *     identity to the server, so the client no longer asserts an id out of
 *     `localStorage`: `loadSession()` asks, and the three answers are three screens
 *     (not admitted / admitted with no name / carry on). Taking a name is what
 *     reloads the role, the characters and the scene — a name that is set with
 *     nothing loaded behind it is the bug this half was written for.
 *  2. **A perspective change loads its scene, in every role.** The
 *     `entityId` watcher skipped `initLocation()` when `gmMode` was set, on the
 *     theory that the GM's own switch path loads its own scene. But the settings
 *     character picker (`beginCharacterSwitch`) has no other location load, so
 *     the perspective moved and the map did not.
 *
 * The App.vue half is checked by extracting the shipped source of the watcher,
 * `switchPerspective` and the injected `locationInit` and executing them against
 * stubs — the same text that ships, so the check can only pass if the real
 * ordering is right. `locationInit` is included because the picker reaches the
 * scene through it when re-picking the character you already act as (no ref
 * changes, so no watcher run). The identity half runs the shipped composable
 * against a stubbed `fetch`, because the server's answer *is* the input now.
 */
import { readFileSync } from 'node:fs'
import { ref } from 'vue'
import { usePlayerIdentity } from '../src/composables/usePlayerIdentity.js'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}
const yes = (name, got) => ok(name, !!got, true)

// ── 1. arriving, taking a name, and what loads with it ───────────────────
// SEC-3 made the server the only source of identity, so the answers it can give
// are the whole test. `fetch` is stubbed per URL rather than mocked wholesale, so
// the assertions can also see *which* request the client decided to make.
console.log('\narrival → identity → what follows\n')

function identityWorld({ session = null, roster = [], taken = null, claim = null } = {}) {
  const playerId = ref('')
  const playerName = ref('')
  const showLoginOverlay = ref(false)
  const calls = []
  const requests = []
  const reply = (ok_, body) => ({ ok: ok_, status: ok_ ? 200 : 400, json: async () => body })

  globalThis.fetch = async (url, opts = {}) => {
    requests.push(`${opts.method || 'GET'} ${url}`)
    // `session === null` is the 401 the perimeter answers: no login screen can fix
    // a missing cookie, so the composable must not treat it as "somebody new".
    if (url === '/api/v1/auth/session') {
      return session ? reply(true, session) : { ok: false, status: 401, json: async () => ({}) }
    }
    if (url === '/api/v1/auth/roster') return reply(true, roster)
    if (url.startsWith('/api/v1/auth/take/')) return reply(!!taken, { player: taken })
    if (url === '/api/v1/auth/claim') return reply(!!claim, { player: claim })
    return reply(false, {})
  }

  const identity = usePlayerIdentity({
    playerId, playerName, showLoginOverlay,
    onIdentityChanged: async () => { calls.push('what-follows') },
  })
  return { ...identity, calls, requests, showLoginOverlay, playerId, playerName }
}

{
  const w = identityWorld({ session: { admitted: true, player: { id: 'player-1', name: 'PTDave' } } })
  await w.loadSession()
  ok('a session carrying a name is the identity', [w.playerId.value, w.playerName.value], ['player-1', 'PTDave'])
  ok('and the overlay stays out of the way', w.showLoginOverlay.value, false)
  ok('and everything derived from it is re-read', w.calls, ['what-follows'])
}

{
  const w = identityWorld({ session: { admitted: true, player: null }, roster: [{ id: 'p1', name: 'A' }] })
  await w.loadSession()
  ok('an admitted device with no name gets the roster', w.showLoginOverlay.value, true)
  ok('and the roster is what it is offered', w.roster.value.map((r) => r.name), ['A'])
  ok('with nothing derived loaded yet — there is no one to load it for', w.calls, [])
}

{
  const w = identityWorld()
  await w.loadSession()
  ok('a refused session is not admitted', w.admitted.value, false)
  ok('and no player is invented from storage', [w.playerId.value, w.showLoginOverlay.value], ['', true])
}

// Taking a name is the act the old flow did by typing one. That is the hole
// SEC-3 closed: the server decides, and the client only asks.
{
  const w = identityWorld({ taken: { id: 'player-2', name: 'Someone' } })
  const took = await w.takePlayer('player-2')
  ok('taking a name sets it', [took, w.playerId.value, w.playerName.value], [true, 'player-2', 'Someone'])
  ok('and it is one POST, to the server', w.requests, ['POST /api/v1/auth/take/player-2'])
  ok('and the new identity reloads what follows', w.calls, ['what-follows'])
  ok('taking who you already are asks the server nothing', await w.takePlayer('player-2'), true)
  ok('  …and made no second request', w.requests.length, 1)
}

{
  const w = identityWorld({ taken: null })
  ok('a take the server refuses changes nothing',
    [await w.takePlayer('nope'), w.playerId.value, w.calls], [false, '', []])
  ok('  …and says so', w.identityError.value.length > 0, true)
}

{
  const w = identityWorld({ claim: { id: 'player-3', name: 'Newcomer' } })
  w.newName.value = '  Newcomer  '
  const claimed = await w.claimPlayer()
  ok('a new name is claimed from the draft', [claimed, w.playerId.value], [true, 'player-3'])
  ok('and the draft is cleared with it', w.newName.value, '')
  ok('and it reloads what follows too', w.calls, ['what-follows'])
  ok('a blank draft claims nothing', await w.claimPlayer(), false)
}

// The settings overlay's switch: the name plate opens the roster, and Back leaves
// it. This is the half of the overlay the styling change sits in.
{
  const w = identityWorld({ roster: [{ id: 'p1', name: 'A' }] })
  await w.beginSwitch()
  ok('the name plate opens the picker on the roster', [w.rosterPicking.value, w.roster.value.length], [true, 1])
  w.endSwitch()
  ok('and Back comes out of it', w.rosterPicking.value, false)
}

// The settings overlay's identity block, which SEC-3 rebuilt: the mechanics became
// the roster (`beginSwitch` above), and the *styling* went with it — a green
// "— switch player" button and a paragraph, where the overlay had always shown the
// player as a name plate. The plate is back; the paragraph lives in its tooltip.
console.log('\nthe name plate\n')

const SRC = readFileSync('src/App.vue', 'utf8')
const CSS = readFileSync('src/assets/styles.css', 'utf8')

yes('the overlay shows the player as the name plate it always was',
  /class="search-wrapper settings-name-wrapper"[\s\S]{0,240}?class="settings-name-static"[\s\S]{0,80}?\{\{ playerName \}\}/.test(SRC))
yes('and the plate is what opens the picker',
  /class="settings-name-static" @click="beginSwitch"/.test(SRC))
yes('styled as a plate — display face, wide tracking',
  /\.settings-name-static \{[\s\S]{0,240}?font-family: var\(--font-display\)/.test(CSS)
  && /\.settings-name-static \{[\s\S]{0,240}?letter-spacing: 3px/.test(CSS))
yes('with the rule SEC-3 enforces riding in its tooltip',
  /title="Switch player[^"]*architect accounts are never takeable"/.test(SRC))
ok('the "You are" section and its switch button are gone',
  /<label class="settings-label">You are<\/label>/.test(SRC), false)
ok('and so is the paragraph that stood under them',
  /<p class="name-hint">\s*Taking another name/.test(SRC), false)

// ── 2. a perspective change loads its scene, in every role ───────────────
console.log('\nperspective → scene load\n')

const script = SRC.match(/<script setup>([\s\S]*?)<\/script>/)[1]
const watcherBody = script.match(/watch\(entityId, \(\) => \{([\s\S]*?)\n\}, \{ flush: 'sync' \}\)/)[1]
const switchBody = script.match(/async function switchPerspective\(id\) \{([\s\S]*?)\n\}/)[1]
const locationInitBody = script.match(/locationInit: \{([\s\S]*?)\n  \},/)[1]

/**
 * The shipped statements, run against stubs. `entityId` is a ref-like whose
 * setter mimics Vue: it fires the watcher only when the value actually changes
 * (that is what makes re-picking the same character a distinct case).
 */
const compileWorld = (watcherSource) => new Function('deps', `
  const { gmMode: gmModeValue, initialEntityId, initialLocationId, entityLocations, playerId: playerIdValue } = deps
  const calls = []
  let _entityId = initialEntityId
  let locationInitPromise = null
  let skipLocationInit = false
  const entityId = {
    get value() { return _entityId },
    set value(v) { if (Object.is(_entityId, v)) return; _entityId = v; runWatcher() },
  }
  const gmMode = { value: gmModeValue }
  const currentLocationId = { value: initialLocationId }
  const viewingEntityId = { value: 'inspecting-something' }
  const playerId = { value: playerIdValue }
  const localStorage = { setItem() {}, removeItem() {} }
  const initLocation = () => { calls.push('init:' + _entityId); return Promise.resolve('init') }
  const refreshDiceBonuses = () => { calls.push('bonuses') }
  const graphql = async (q, vars) => ({ entity: { currentLocation: (entityLocations || {})[vars.id] ?? null } })
  const fetch = () => Promise.resolve()
  function runWatcher() { ${watcherSource} }
  async function switchPerspective(id) { ${switchBody} }
  const locationInit = {${locationInitBody}}
  return { entityId, currentLocationId, viewingEntityId, playerId, calls, switchPerspective, locationInit }
`)

const makeWorld = compileWorld(watcherBody)

const w1 = makeWorld({ gmMode: true, initialEntityId: null, initialLocationId: 'loc-krasnoyarsk', entityLocations: { 'character-20809': 'loc-yinling' } })
w1.entityId.value = 'character-20809'
ok('a GM assuming a character loads that character\'s scene', w1.calls, ['init:character-20809', 'bonuses'])

const w1p = makeWorld({ gmMode: false, initialEntityId: null, initialLocationId: 'loc-a', entityLocations: { x: 'loc-b' } })
w1p.entityId.value = 'x'
ok('a player switching character still loads the scene', w1p.calls, ['init:x', 'bonuses'])

const w2 = makeWorld({ gmMode: true, initialEntityId: 'character-x', initialLocationId: 'loc-b', entityLocations: {} })
w2.entityId.value = null
ok('a GM returning to free-roam keeps the scene (no reload)', w2.calls, [])

// switchPerspective: one load, no flash, and still correct when nothing changes
const w3 = makeWorld({ gmMode: true, initialEntityId: null, initialLocationId: 'loc-a', entityLocations: { y: 'loc-b' } })
await w3.switchPerspective('y')
ok('assuming an entity elsewhere loads exactly once', w3.calls, ['init:y', 'bonuses'])
ok('assuming clears the read-only inspect', w3.viewingEntityId.value, null)

const w4 = makeWorld({ gmMode: true, initialEntityId: 'x', initialLocationId: 'loc-a', entityLocations: { y: 'loc-a' } })
await w4.switchPerspective('y')
ok('assuming an entity already on screen does not reload (no LOADING flash)', w4.calls, [])

const w5 = makeWorld({ gmMode: true, initialEntityId: 'x', initialLocationId: 'loc-a', entityLocations: { x: 'loc-b' } })
await w5.switchPerspective('x')
ok('re-assuming the same entity lands where it is', w5.calls, ['init:x'])

// the skip flag must not leak into the next assumption
const w6 = makeWorld({ gmMode: true, initialEntityId: 'x', initialLocationId: 'loc-a', entityLocations: { y: 'loc-a', z: 'loc-c' } })
await w6.switchPerspective('y')   // same location → skipped
w6.entityId.value = 'z'
ok('the same-location skip does not leak to the next assumption', w6.calls, ['init:z', 'bonuses'])

// the picker reaches the scene through locationInit when no ref changes
const w7 = makeWorld({ gmMode: true, initialEntityId: 'x', initialLocationId: 'loc-a', entityLocations: {} })
w7.locationInit.reset()
w7.entityId.value = 'x'           // re-picking the character already acted as
const p7 = w7.locationInit.current()
ok('re-picking the character you act as still loads their scene', typeof p7?.then, 'function')
ok('  …and that load is the one for them', w7.calls, ['init:x'])

// ── 3. the check can actually fail ───────────────────────────────────────
// Run the pre-fix watcher — `if (gmMode.value || !entityId.value) return` —
// through the same world. It must NOT load the scene, which is both the bug the
// human hit and the proof that the passing cases above are not vacuous.
console.log('\ncheck sensitivity\n')
const oldGuard = watcherBody.replace(
  'if (!entityId.value || skipLocationInit) {',
  'if (gmMode.value || !entityId.value) {'
)
ok('the pre-fix guard is a strict rewrite of the shipped one', oldGuard !== watcherBody, true)

const wOld = compileWorld(oldGuard)({
  gmMode: true, initialEntityId: null, initialLocationId: 'loc-krasnoyarsk',
  entityLocations: { 'character-20809': 'loc-yinling' },
})
wOld.entityId.value = 'character-20809'
ok('pre-fix: a GM assuming a character stayed put (the reported bug)', wOld.calls, [])

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
