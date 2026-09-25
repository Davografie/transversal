/**
 * Executable check for toast audiences ([[P2.15]]).
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Mount over `/app` (not `/work`) so the
 * image's `node_modules` still resolves `vue`:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-toast-audience.mjs
 *
 * It pins the one thing that is easy to get subtly wrong about centralising the
 * role filtering: the role must be read *when the toast is added*, not when the
 * composable is created (the app creates it before `gmMode` settles), and a
 * filtered toast must not consume a slot in the visible list.
 */

import { useToasts } from '../src/composables/useToasts.js'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  if (same) pass++
  else { fail++; console.error(`FAIL ${name}\n  got  ${JSON.stringify(got)}\n  want ${JSON.stringify(want)}`) }
}

// A stand-in for `gmMode`: the composable reads it through a getter.
let gm = false
const { toasts, addToast } = useToasts({ maxToasts: 5, ttlMs: 0, isGm: () => gm })

// ── the player's view ────────────────────────────────────────────────
addToast('session started')                 // audience defaults to all
addToast('difficulty set', 'roll', 'player')
addToast('beat ended', 'dice', 'gm')
ok('player sees all + player, not gm', toasts.value.map(t => t.message), ['session started', 'difficulty set'])
ok('the audience rides on the toast', toasts.value.map(t => t.audience), ['all', 'player'])

// ── the same composable, now looking as the GM ───────────────────────
gm = true
addToast('a player rolled', 'roll', 'gm')
addToast('you have been challenged', 'dice', 'player')
ok('gm sees gm but not player', toasts.value.map(t => t.message),
  ['session started', 'difficulty set', 'a player rolled'])
ok('the role is read at add time, not creation time',
  toasts.value.some(t => t.message === 'a player rolled'), true)

// ── a filtered toast must not eat a visible slot ─────────────────────
gm = false
const before = toasts.value.length
addToast('gm only', 'dice', 'gm')
ok('a filtered toast adds nothing', toasts.value.length, before)

// ── the cap still holds, and the newest survives it ──────────────────
gm = true
for (let i = 0; i < 8; i++) addToast(`gm ${i}`, 'dice', 'gm')
ok('the cap holds on visible toasts', toasts.value.length, 5)
ok('the newest is kept', toasts.value.at(-1).message, 'gm 7')

console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
