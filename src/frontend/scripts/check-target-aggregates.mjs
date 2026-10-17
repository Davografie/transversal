/**
 * Executable check: **the editor offers the aggregates the server will resolve.**
 *
 * `closest` ranks a collection of places by distance and reads no field, so it is
 * constrained by the *element* rather than by a field type. Two declarations have
 * to agree for that to reach an author: the API's `acceptsElements` and the
 * editor's filter over it. When they disagree the failure is quiet in the worst
 * way — the function simply is not in the dropdown, which reads as "not built"
 * rather than "not offered here" ([[B328]]).
 *
 * The server half is pinned by `tests/test_closest_aggregate.py`; this is the UI
 * half, which no Python test can see.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const SRC = fileURLToPath(new URL('../src', import.meta.url))
const catalog = readFileSync(`${SRC}/composables/useTargetCatalog.js`, 'utf8')
const builder = readFileSync(`${SRC}/components/gm/TargetSpecBuilder.vue`, 'utf8')

let failed = 0
const ok = (name, got, want = true) => {
  const pass = got === want
  console.log(`  ${pass ? 'PASS' : 'FAIL'}  ${name}`)
  if (!pass) failed += 1
}

// The query must ask for it, or the field is `undefined` on every row and the
// filter silently treats an absent list as "no constraint".
ok('the catalog query selects acceptsElements',
  /aggregations\s*\{[^}]*acceptsElements/.test(catalog))

// And the filter must use it on the *no-field* path — a field function is
// constrained by its field type instead, which is a different question.
const fn = builder.slice(builder.indexOf('function aggregationsForField('))
const body = fn.slice(0, fn.indexOf('\n}') + 2)
ok('the no-field branch filters by the collection\'s element',
  /acceptsElements/.test(body) && /priorElement\(i\)/.test(body))
ok('…and a chosen field still wins the constraint',
  /a\.needsField/.test(body) && /a\.accepts/.test(body))

console.log(failed ? `${failed} failed` : 'all clear')
process.exit(failed ? 1 : 0)
