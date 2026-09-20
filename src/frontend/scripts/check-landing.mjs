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
 * Two bugs, both invisible to the build and both reported from live testing:
 *
 *  1. **Logging in dropped you straight into the game.** `confirmPlayer` closed
 *     the overlay whenever `needsCharacterPick` was false — which is always true
 *     for an architect (`gmMode`), and true for anyone whose perspective was
 *     already restored. You never got the character picker, so you never got to
 *     choose where to begin.
 *  2. **A GM assuming a character stayed where they were roaming.** The
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
 * changes, so no watcher run).
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
const tick = () => new Promise((r) => setTimeout(r, 5))

// Minimal localStorage — `usePlayerIdentity` and the App watcher both write it.
globalThis.localStorage = {
  _m: new Map(),
  getItem(k) { return this._m.has(k) ? this._m.get(k) : null },
  setItem(k, v) { this._m.set(k, String(v)) },
  removeItem(k) { this._m.delete(k) },
}

// ── 1. logging in lands on the character select ──────────────────────────
console.log('\nlogin → character select\n')

function loginWorld({ role = 'architect', restoredEntityId = null } = {}) {
  const showLoginOverlay = ref(true)
  const playerId = ref('')
  const playerName = ref('')
  const entityId = ref(restoredEntityId)
  const calls = []
  const stub = (label) => () => { calls.push(label); return Promise.resolve() }
  const identity = usePlayerIdentity({
    playerId, playerName, showLoginOverlay, entityId,
    loadPlayerRole: () => { calls.push('role:' + role); return Promise.resolve() },
    initLocation: stub('initLocation'),
    fetchPlayerEntities: stub('entities'),
    fetchSupportCharacters: stub('support'),
    fetchActiveMains: stub('mains'),
    fetchEntitiesFor: stub('entitiesFor'),
    pendingPlayerEntities: ref([]),
  })
  // Pick an existing player exactly as the search suggestion does.
  identity.selectSuggestion({ id: 'player-bc80b9', name: 'PTDave' })
  return { ...identity, calls, showLoginOverlay, playerId }
}

for (const [role, restored] of [['architect', null], ['architect', 'character-20809'], ['player', null], ['player', 'character-20809']]) {
  const w = loginWorld({ role, restoredEntityId: restored })
  w.confirmPlayer()
  await tick()
  ok(`after login (${role}, restored ${restored}) the selector is still up`, w.showLoginOverlay.value, true)
  ok(`after login (${role}, restored ${restored}) the player is set`, w.playerId.value, 'player-bc80b9')
  ok(`after login (${role}, restored ${restored}) the lists load for it`, w.calls.sort(), ['entities', 'mains', 'role:' + role, 'support'])
}

// ── 2. a perspective change loads its scene, in every role ───────────────
console.log('\nperspective → scene load\n')

const SRC = readFileSync('src/App.vue', 'utf8')
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
