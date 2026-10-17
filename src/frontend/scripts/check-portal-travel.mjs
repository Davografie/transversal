/**
 * Executable check: **a portal navdot carries its effects on every travel path.**
 *
 * `travelWithAnimation` hands `child.effects` to `relocate`, which fires
 * `/portal/{to}/fire` only when that list is non-empty. There are two ways a
 * traveller reaches a navdot and both must pass the effects through:
 *
 *   - `sendOccupant` — a GM sends *someone else* through the dot, via
 *     `travelDescriptor`, which carries `effects: nd.target.effects`;
 *   - `travelToTarget` — the traveller is the character you are **playing**, via a
 *     synthesised child object. It omitted `effects`, so dropping your own
 *     character on a portal moved them and never fired the portal, while the same
 *     drop on someone else worked (2026-10-17).
 *
 * The failure is silent in both directions — the traveller moves either way — which
 * is exactly why it is pinned here rather than left to a click.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const SRC = fileURLToPath(new URL('../src', import.meta.url))
const viewer = readFileSync(`${SRC}/components/LocationViewer.vue`, 'utf8')

let failed = 0
const ok = (name, got, want = true) => {
  const pass = got === want
  console.log(`  ${pass ? 'PASS' : 'FAIL'}  ${name}`)
  if (!pass) failed += 1
}

const body = (startMarker, endMarker) => {
  const a = viewer.indexOf(startMarker)
  const b = endMarker ? viewer.indexOf(endMarker, a) : viewer.length
  return a < 0 ? '' : viewer.slice(a, b < 0 ? viewer.length : b)
}

const travelToTarget = body('function travelToTarget(', '\nfunction ')
const travelDescriptor = body('function travelDescriptor(', '\nfunction ')
const sendOccupant = body('async function sendOccupant(', '\nasync function ')

// The two paths that build a destination for `travelWithAnimation` / the fire call.
ok('the self-travel path passes the portal\'s effects',
  /effects:\s*nd\.target\.effects/.test(travelToTarget))
ok('…and so does the descriptor for someone else',
  /effects:\s*nd\.target\.effects/.test(travelDescriptor))
ok('sending an occupant fires the portal when it has effects',
  /desc\.effects\?\.length/.test(sendOccupant))
ok('the animation forwards the child\'s effects to the relocate',
  /travelWithAnimation[\s\S]{0,1200}?child\.effects/.test(viewer) ||
  /relocate\(child\._key[^)]*child\.effects/.test(viewer))

console.log(failed ? `${failed} failed` : 'all clear')
process.exit(failed ? 1 : 0)
