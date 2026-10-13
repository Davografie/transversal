/**
 * Executable check for the roll-table panels' header badge / copy-ID chip.
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image, the same
 * way as the other checks:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-roll-table-badges.mjs
 *
 * The request: "The roll table panel should show a copy-ID [roll-table] chip in
 * the header like the other panels."
 *
 * `Panel.vue` renders `spec.badge` as a header chip and, **when the panel has an
 * `id`**, makes that chip the copy-ID control (`is-copyable`, `copyId()`, the ✓
 * swap). Every other panel family passes both — `GmLifePathDetailPanel` is opened
 * with `id` + `badge: 'LIFE-PATH'`, SFX with `id` + `badge: 'SFX'` — but the
 * roll-table family passed neither, so the chip never rendered. The openers
 * already carried the table `id`; they were only missing the badge. (The
 * read-only detail panel has since been folded into `GmRollTableEditPanel`, so
 * the family is one panel and these checks read the unified openers.)
 *
 * The assertions below read the openers out of the shipping `.vue` files, so the
 * rule is checked where it is written rather than restated.
 */
import { readFileSync } from 'node:fs'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}

const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8')
const PANEL = read('../src/components/gm/Panel.vue')
const FILES = {
  'GmLifePathDetailPanel.vue': read('../src/components/gm/GmLifePathDetailPanel.vue'),
  'GmRollTableGroupPanel.vue': read('../src/components/gm/GmRollTableGroupPanel.vue'),
  'RelationalCanvas.vue': read('../src/components/canvas/RelationalCanvas.vue'),
}

/** Every `panel.open({ … })` argument block in a file, brace-balanced. */
function openCalls(src) {
  const out = []
  const re = /panel\.open\(/g
  let m
  while ((m = re.exec(src))) {
    const start = src.indexOf('{', m.index)
    if (start < 0) continue
    let depth = 0
    let i = start
    for (; i < src.length; i++) {
      if (src[i] === '{') depth++
      else if (src[i] === '}') { depth--; if (!depth) { i++; break } }
    }
    out.push(src.slice(m.index, i))
    re.lastIndex = i
  }
  return out
}

const calls = Object.entries(FILES).flatMap(([file, src]) =>
  openCalls(src).map((block) => ({ file, block })))

const detailCalls = calls.filter(c => /component:\s*GmRollTableDetailPanel\b/.test(c.block))
const editCalls = calls.filter(c => /component:\s*GmRollTableEditPanel\b/.test(c.block))

// ── 1. the unified panel — the chip and the id it copies ────────────────
// `GmRollTableDetailPanel` was folded into `GmRollTableEditPanel` (B275), so
// every opener now lands in the editor and there is no detail panel left.
console.log('\nUnified roll-table openers — badge + copyable id\n')

ok('no opener still references the deleted detail panel', detailCalls.length, 0)
ok('every opener of the unified panel was found (5 calls)', editCalls.length, 5)
ok('each passes the badge', editCalls.map(c => /badge:\s*'ROLL-TABLE'/.test(c.block)), [true, true, true, true, true])

// Call order follows FILES above: life-path table, group table, canvas table.
// The life-path opener now names the *step's* table (`step.tableId`) — the
// detail panel's steps list is the wrapper, and a path may wrap one table twice,
// so the step is the identity it holds (B277). The intent is unchanged: an
// existing-table opener passes the table id the chip copies.
ok('each existing-table opener passes the table id, which is what the chip copies',
  editCalls.filter(c => /id:\s*\S/.test(c.block))
    .map(c => (c.block.match(/id:\s*([^,\n]+)/) || [])[1].trim()),
  ['step.tableId', 't.id', 'tableId'])
ok('only the two create openers omit the id — there is nothing to copy yet',
  editCalls.filter(c => !/id:\s*\S/.test(c.block)).map(c => c.file).sort(),
  ['GmLifePathDetailPanel.vue', 'GmRollTableGroupPanel.vue'])

// ── 3. the mechanism: badge renders the chip, id makes it copy ──────────
console.log('\nPanel.vue — the chip renders on the badge and copies the id\n')

ok('the chip is gated on the badge', /v-if="spec\?\.badge"/.test(PANEL), true)
ok('it is marked copyable only when the panel has an id', /'is-copyable':\s*!!id/.test(PANEL), true)
ok('clicking it copies', /@click="id && copyId\(\)"/.test(PANEL), true)
ok('the tooltip names the id', /Copy ID \(\$\{id\}\)/.test(PANEL), true)
ok('and the label swaps for a ✓ while copied', /\{\{\s*copied && id \? '✓' : spec\.badge\s*\}\}/.test(PANEL), true)

// The pre-fix shape, which must show nothing: the detail openers carried an id
// but no badge, so the gate never opened.
const chip = (spec) => ({ shows: !!spec.badge, copyable: !!spec.id })
ok('pre-fix: an opener with an id but no badge renders no chip at all',
  chip({ title: 'Iron Roots', id: 'rt-123' }), { shows: false, copyable: true })
ok('shipped: adding the badge renders the chip, still copyable',
  chip({ title: 'Iron Roots', id: 'rt-123', badge: 'ROLL-TABLE' }), { shows: true, copyable: true })

// ── 4. nothing in the family was left behind ────────────────────────────
console.log('\nNo roll-table opener is left without a badge\n')

const unbaged = calls
  .filter(c => /component:\s*GmRollTableEditPanel\b/.test(c.block))
  .filter(c => !/badge:/.test(c.block))
  .map(c => `${c.file}: ${c.block.split('\n')[0].trim()}`)
ok('every roll-table panel open carries a badge', unbaged, [])

console.log(`\n${pass} passed, ${fail} failed\n`)
process.exit(fail ? 1 : 0)
