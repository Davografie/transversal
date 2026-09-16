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
