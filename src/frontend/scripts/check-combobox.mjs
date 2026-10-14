/**
 * Executable check for the shared autocomplete core (`useCombobox`).
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Unlike the pure-util checks this one
 * imports Vue, so it runs against the image's `node_modules` with the source
 * mounted over it:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-combobox.mjs
 *
 * It pins the semantics that are easy to get subtly wrong and that the three
 * shells (SearchDropdown, TagInput, the GM panel's filter) all depend on: what
 * is excluded from the list, the create row, how free text resolves, the two
 * highlight modes, and the two async rules — a query function is authoritative
 * (its results are not re-filtered here), and a superseded response can never
 * overwrite a newer one.
 */
import { ref } from 'vue'
import { useCombobox } from '../src/composables/useCombobox.js'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}
const tick = () => new Promise((r) => setTimeout(r, 5))
const values = (c) => c.available.value.map((i) => i.value)

console.log('\nuseCombobox')

// ── the list ────────────────────────────────────────────────────────────
{
  const options = ref([
    { value: 'alpha', label: 'Alpha' },
    { value: 'beta', label: 'Beta' },
    { value: 'gamma', label: 'Gamma' },
    { value: 'alphabet', label: 'Alphabet' },
  ])
  const c = useCombobox({ options, query: ref(''), chosen: ref(['beta']) })
  ok('lists everything not already chosen', values(c), ['alpha', 'gamma', 'alphabet'])

  const q = ref('alp')
  const filtered = useCombobox({ options, query: q, chosen: ref(['beta']) })
  ok('filters on the label', values(filtered), ['alpha', 'alphabet'])

  const capped = useCombobox({ options, query: ref('a'), maxResults: 2 })
  ok('maxResults caps the list', values(capped).length, 2)

  const extra = useCombobox({ options, query: ref(''), exclude: ref(['alpha', 'gamma']) })
  ok('excludeIds removes values too', values(extra), ['beta', 'alphabet'])
}

// ── pageSize: the window grows instead of the list being cut ────────────
// The GM panel's filter used `maxResults: 10`, which truncated the match set in
// database order: with 21 rows matching "wang", the last ten Wang GMCs could not
// be reached by typing anything at all. `pageSize` reveals the same list a window
// at a time, so nothing is unreachable — it is just not all rendered at once.
console.log('\npageSize — a window that grows\n')

{
  const options = ref(Array.from({ length: 25 }, (_, i) => `opt${String(i).padStart(2, '0')}`))
  const query = ref('opt')
  const c = useCombobox({ options, query, pageSize: 10 })
  ok('one page is revealed', values(c).length, 10)
  ok('and it knows the match set runs on', c.hasMore.value, true)

  c.loadMore()
  ok('loadMore reveals the next page', values(c).length, 20)
  c.loadMore()
  ok('the last page ends where the match set does', [values(c).length, c.hasMore.value], [25, false])
  c.loadMore()
  ok('loading past the end is a no-op', values(c).length, 25)

  query.value = 'o'
  ok('a new query starts at one page again', [values(c).length, c.hasMore.value], [10, true])
}

// ── requireQuery ────────────────────────────────────────────────────────
{
  const c = useCombobox({ options: ref(['a', 'b']), query: ref(''), requireQuery: true })
  ok('requireQuery lists nothing until typed', values(c), [])
  ok('requireQuery leaves nothing to commit', c.optionCount.value, 0)
}

// ── create row and resolving free text ──────────────────────────────────
{
  const options = ref(['earth', 'three realms'])
  const query = ref('mars')
  const free = useCombobox({ options, query, allowCustom: true })
  ok('free text offers a create row', free.createText.value, 'Create “mars”')
  ok('the create row counts as an option', free.optionCount.value, 1)
  ok('resolve accepts free text', free.resolve('mars'), 'mars')
  ok('resolve maps a label to its value', free.resolve('Three Realms'), 'three realms')
  ok('labelFor renders a stored value', free.labelFor('earth'), 'earth')

  query.value = 'earth'
  ok('an exact match suppresses the create row', free.createText.value, '')

  const restricted = useCombobox({ options, query: ref('mars'), allowCustom: false })
  ok('restricted refuses free text', restricted.resolve('mars'), null)
  ok('restricted has no create row', restricted.createText.value, '')
  ok('restricted still resolves a listed value', restricted.resolve('EARTH'), 'earth')
}

// ── highlight: wrap vs clamp ────────────────────────────────────────────
{
  const mk = (wrapHighlight) => {
    const c = useCombobox({ options: ref(['a', 'b', 'c']), query: ref(''), wrapHighlight })
    c.armTop()
    return c
  }
  const wrapped = mk(true)
  const clamped = mk(false)
  ok('armTop arms the first option', [wrapped.highlighted.value, clamped.highlighted.value], [0, 0])

  wrapped.move(-1); clamped.move(-1)
  ok('wrapping walks off the end to nothing', wrapped.highlighted.value, -1)
  ok('clamping stays on the first option', clamped.highlighted.value, 0)

  for (let i = 0; i < 9; i++) clamped.move(1)
  ok('clamping stops at the last option', clamped.highlighted.value, 2)
}

// A paged list must not re-arm the highlight when a page is revealed: a keyboard
// user walking to the end of a page would be thrown back to its first row. The
// arm-on-change watch is on the match set, not on the rendered window.
{
  const options = ref(Array.from({ length: 25 }, (_, i) => `opt${String(i).padStart(2, '0')}`))
  const c = useCombobox({ options, query: ref('opt'), pageSize: 10, wrapHighlight: false })
  c.armTop()
  ok('arming starts on the first row', c.highlighted.value, 0)

  for (let i = 0; i < 9; i++) c.move(1)
  ok('stepping onto the last revealed row loads the next page and stays there',
    [c.highlighted.value, values(c).length], [9, 20])

  for (let i = 0; i < 10; i++) c.move(1)
  ok('…and it walks the whole list, paging again at its next end',
    [c.highlighted.value, values(c).length, c.hasMore.value], [19, 25, false])
}

// ── async: authoritative results, and the stale-response guard ──────────
{
  const pending = []
  const options = ref((q) => new Promise((resolve) => pending.push({ q, resolve })))
  const query = ref('a')
  const c = useCombobox({ options, query, debounceMs: 0 })

  await tick()
  query.value = 'ab'
  await tick(); await tick()
  ok('the query function is called per query', pending.map((p) => p.q), ['a', 'ab'])

  // Resolve the OLDER request last: it must not overwrite the newer result.
  const older = pending[0]
  const newer = pending[pending.length - 1]
  newer.resolve([{ value: 'fresh', label: 'Fresh' }])
  await tick()
  ok('the newest result lands', values(c), ['fresh'])

  older.resolve([{ value: 'stale', label: 'Stale' }])
  await tick()
  ok('a superseded response cannot overwrite it', values(c), ['fresh'])

  // The server matched; the core must not re-filter its answers (this is what
  // silently dropped rows when the two disagreed).
  ok('a query function\u2019s results are not re-filtered', values(c), ['fresh'])
  ok('loading clears when the query settles', c.loading.value, false)
}

console.log(`\n  ${pass} passed, ${fail} failed\n`)
process.exit(fail ? 1 : 0)
