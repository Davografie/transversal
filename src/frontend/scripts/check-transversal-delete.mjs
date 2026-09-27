/**
 * Executable check for deleting a transversal link from the GM entity panel.
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image, the same
 * way as the other checks:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-transversal-delete.mjs
 *
 * The request: "I need to be able to delete transversal links in the GM entity
 * edit panel for locations."
 *
 * The panel listed a location's transversals with a portal-effects button and a
 * type toggle, and **no way to remove one** — the create and toggle calls existed
 * in `useTransversalLinks`, the delete was simply never written. The backend
 * route was already there: `DELETE /locations/{from}/edges/{to}`, which removes
 * the reverse edge too. Two contract details are easy to get wrong and are
 * asserted below: `type` is a **query** parameter on DELETE (defaulting to
 * `super`, so a transversal must name itself), and the destination id is
 * `link._key` — a `transversal` entry in the navigate payload *is* the target
 * location document, which is also what the type toggle passes.
 *
 * The rules below are lifted out of the shipping files and run, so this is the
 * shipped logic rather than a restatement of it.
 */
import { readFileSync } from 'node:fs'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}

const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8')
const COMPOSABLE = read('../src/composables/useTransversalLinks.js')
const ENTRY = read('../src/components/gm/GmEntityEditPanel.vue')

function between(src, from, to) {
  const i = src.indexOf(from)
  if (i < 0) throw new Error(`not found: ${from}`)
  const j = src.indexOf(to, i)
  if (j < 0) throw new Error(`not found: ${to}`)
  return src.slice(i, j)
}

const DELETE_SRC = between(COMPOSABLE, 'async function deleteTransversalLink(fromId, toId) {', '\n  async function toggleTransversalType')
const REMOVE_SRC = between(ENTRY, 'async function removeTransversalLink(link) {', '\nfunction openPortalConfig')

const makeDelete = new Function('fetch', `
  const API_BASE = '/api/v1'
  ${DELETE_SRC}
  return deleteTransversalLink
`)
const makeRemove = new Function('ctx', `
  const { armOrConfirm, tieBusy, transversalNote, deleteTransversalLink, loadTransversalLinks, props } = ctx
  ${REMOVE_SRC}
  return removeTransversalLink
`)

function stubFetch({ ok = true, status = 200, json } = {}) {
  const calls = []
  const fn = async (url, opts = {}) => {
    calls.push({ url, method: opts.method })
    return { ok, status, json: async () => { if (json === undefined) throw new Error('no body'); return json } }
  }
  return { fn, calls }
}

// ── 1. the API call ─────────────────────────────────────────────────────
console.log('\nuseTransversalLinks — the DELETE it sends\n')

{
  const s = stubFetch({ ok: true })
  await makeDelete(s.fn)('loc-a', 'loc-b')
  ok('one call', s.calls.length, 1)
  ok('it is a DELETE', s.calls[0].method, 'DELETE')
  ok('it names the edge type, or the route looks for a parent edge',
    s.calls[0].url, '/api/v1/locations/loc-a/edges/loc-b?type=transversal')
}

{
  const s = stubFetch({ ok: false, status: 404, json: { detail: "Edge 'loc-a' -> 'loc-b' (transversal) not found" } })
  const err = await makeDelete(s.fn)('loc-a', 'loc-b').then(() => null, (e) => e)
  ok('a refusal surfaces the server reason, not the raw body',
    err?.message, "Edge 'loc-a' -> 'loc-b' (transversal) not found")
}

{
  const s = stubFetch({ ok: false, status: 500 })  // json() throws
  const err = await makeDelete(s.fn)('loc-a', 'loc-b').then(() => null, (e) => e)
  ok('a non-JSON failure still reports something readable',
    err?.message, 'Could not remove that link (500)')
}

// ── 2. the row handler ──────────────────────────────────────────────────
console.log('\nGmEntityEditPanel — removeTransversalLink\n')

async function removeCase({ confirm, fail = false }) {
  const calls = { deleted: [], reloads: 0 }
  const ctx = {
    armOrConfirm: () => confirm,
    tieBusy: { value: '' },
    transversalNote: { value: 'stale note' },
    deleteTransversalLink: async (from, to) => {
      calls.deleted.push([from, to])
      if (fail) throw new Error('already gone')
    },
    loadTransversalLinks: async () => { calls.reloads++ },
    props: { entityId: 'loc-a' },
  }
  await makeRemove(ctx)({ _key: 'loc-b', name: 'Willow Bath' })
  return { ctx, calls }
}

{
  const { calls } = await removeCase({ confirm: false })
  ok('the first click only arms — nothing is deleted', calls.deleted, [])
  ok('and nothing is re-read', calls.reloads, 0)
}

{
  const { ctx, calls } = await removeCase({ confirm: true })
  ok('the second click deletes the (from, to) the route expects',
    calls.deleted, [['loc-a', 'loc-b']])
  ok('and the list is re-read', calls.reloads, 1)
  ok('the note is cleared on success', ctx.transversalNote.value, '')
  ok('and the row is released', ctx.tieBusy.value, '')
}

{
  const { ctx, calls } = await removeCase({ confirm: true, fail: true })
  ok('a failed delete reports the reason', ctx.transversalNote.value, 'already gone')
  ok('and does not re-read a list that did not change', calls.reloads, 0)
  ok('and still releases the row', ctx.tieBusy.value, '')
}

// ── 3. the row control, and the id it deletes ───────────────────────────
console.log('\nGmEntityEditPanel — the row control and the id\n')

const rowBlock = ENTRY.slice(ENTRY.indexOf('class="transversal-row"'), ENTRY.indexOf('class="transversal-add"'))

ok('the row carries a remove control', /removeTransversalLink\(link\)/.test(rowBlock), true)
ok('it is the two-step armed control, not a one-click delete',
  /armedTie === link\._key \? '✓\?' : '✕'/.test(rowBlock), true)
ok('it shows the busy state while the write is in flight',
  /:loading="tieBusy === link\._key"/.test(rowBlock), true)
ok('it names what will be removed', /Confirm: remove the transversal link to \$\{link\.name\}/.test(rowBlock), true)
ok('a failure has somewhere to appear', /v-if="transversalNote"/.test(ENTRY), true)

// The destination id must be the one the rest of the panel already uses: a
// `transversal` entry in the navigate payload is the target location document,
// so `link._key` is a location id — not an edge key.
const toggleArg = (ENTRY.match(/toggleTransversalType\(props\.entityId,\s*([^,]+),/) || [])[1]
const deleteArg = (ENTRY.match(/deleteTransversalLink\(props\.entityId,\s*([^)]+)\)/) || [])[1]
ok('the toggle and the delete agree on which id the target is',
  [toggleArg?.trim(), deleteArg?.trim()], ['link._key', 'link._key'])

// The pre-fix row, which must offer no removal at all.
const PRE_FIX_ROW = `<div class="transversal-row">
  <span class="transversal-name">{{ link.name }}</span>
  <Button class="transversal-effects" title="Edit portal effects">⚙</Button>
  <Button class="transversal-toggle">{{ link.transversal_type || 'inapposite' }}</Button>
</div>`
ok('pre-fix: the row had no way to remove a link',
  /removeTransversalLink/.test(PRE_FIX_ROW), false)
ok('shipped: the same row does', /removeTransversalLink/.test(rowBlock), true)

console.log(`\n${pass} passed, ${fail} failed\n`)
process.exit(fail ? 1 : 0)
