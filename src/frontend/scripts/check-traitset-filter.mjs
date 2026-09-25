/**
 * Executable check for the traitset search scoping both lists.
 *
 * The frontend has no test runner, so this is a plain node script with
 * assertions — no dependency added. Run it against the frontend image:
 *
 *   docker run --rm \
 *     -v /path/to/src/frontend/scripts:/app/scripts:ro \
 *     -v /path/to/src/frontend/src:/app/src:ro \
 *     -w /app transversal2-frontend:latest node scripts/check-traitset-filter.mjs
 *
 * The report: "When I filter on a trait, the traitsets are filtered on which
 * contain that trait, but the trait list in that traitset doesn't filter."
 *
 * `GmTraitsetsPanel` keeps a set when the query matches the set's **name or** any
 * contained trait's name, and opened the detail with only `traitsetId` — so the
 * detail drew every trait of the set. The query now travels with the panel spec
 * (`context`, as the live ref) and the detail scopes its list by it.
 *
 * The rules below are lifted out of the two shipping `.vue` files and run, so
 * this is the shipped logic rather than a restatement of it. The pre-fix shape is
 * run too, and must reproduce the reported symptom, or the pass means nothing.
 */
import { readFileSync } from 'node:fs'

let pass = 0, fail = 0
const ok = (name, got, want) => {
  const same = JSON.stringify(got) === JSON.stringify(want)
  same ? pass++ : fail++
  console.log(`${same ? '  PASS' : '  FAIL'}  ${name}${same ? '' : `\n         got ${JSON.stringify(got)}  want ${JSON.stringify(want)}`}`)
}

const read = (p) => readFileSync(new URL(p, import.meta.url), 'utf8')
const PANEL = read('../src/components/gm/GmTraitsetsPanel.vue')
const DETAIL = read('../src/components/gm/GmTraitsetDetail.vue')

/** The shipped text between two markers, so it can be run as written. */
function between(src, from, to) {
  const i = src.indexOf(from)
  if (i < 0) throw new Error(`not found: ${from}`)
  const j = to ? src.indexOf(to, i) : src.length
  if (j < 0) throw new Error(`not found: ${to}`)
  return src.slice(i, j)
}

// `computed(fn)` → a lazy `{ value }`, so the shipped bodies run without Vue.
const mk = (fn) => ({ get value() { return fn() } })

/**
 * Turn a chunk of shipped component script into a factory: `mk` supplies
 * `computed`, and the factory's own parameters are the refs the chunk closes
 * over, so each case gets a fresh evaluation of the shipped text.
 */
function factory(src, names, returns) {
  return new Function('mk', `
    return (${names.join(', ')}) => {
      ${src.replace(/computed\(/g, 'mk(')}
      return ${returns}
    }
  `)(mk)
}

// ── 1. the panel's rule: which sets survive the search ───────────────────
console.log('\nGmTraitsetsPanel — which sets the query keeps\n')

const panelFiltered = factory(
  between(PANEL, 'const filtered = computed(', '\nfunction onClick'),
  ['search', 'traitsets', 'localOrder'],
  'filtered',
)

const SETS = [
  { id: 'ts-attributes', name: 'Attributes', traits: [{ name: 'Might' }, { name: 'Grace' }, { name: 'Wits' }] },
  { id: 'ts-skills', name: 'Skills', traits: [{ name: 'Fight' }, { name: 'Sneak' }] },
  { id: 'ts-d4', name: 'D4 Tricks', traits: [{ name: 'Nimble' }, { name: 'Feint' }] },
  { id: 'ts-empty', name: 'Empty Set', traits: [] },
]
const idsOf = (search) => panelFiltered({ value: search }, { value: SETS }, null).value.map(s => s.id)

ok('an empty query keeps every set', idsOf(''), SETS.map(s => s.id))
ok('a name match keeps the set', idsOf('skills'), ['ts-skills'])
ok('a trait match keeps its set', idsOf('feint'), ['ts-d4'])
ok('a trait match keeps *every* set holding it', idsOf('ight'), ['ts-attributes', 'ts-skills'])
ok('the match is case-insensitive', idsOf('MIGHT'), ['ts-attributes'])
ok('a set with no traits can only match by name', idsOf('empty'), ['ts-empty'])
ok('a query matching nothing keeps nothing', idsOf('zzz'), [])

// A set can be on screen because of its NAME while a different set is on screen
// because of a TRAIT — the case the two rules below have to tell apart.
const MIXED = [
  { id: 'ts-by-name', name: 'Combat Arts', traits: [{ name: 'Blade' }, { name: 'Bow' }] },
  { id: 'ts-by-trait', name: 'Wilds', traits: [{ name: 'Combat Reflex' }, { name: 'Forage' }] },
]
const mixedIds = (q) => panelFiltered({ value: q }, { value: MIXED }, null).value.map(s => s.id)
ok('one query can reach a set by name and another by trait',
  mixedIds('combat'), ['ts-by-name', 'ts-by-trait'])

// ── 2. the detail's rule: what the opened set lists ──────────────────────
console.log('\nthe opened set — which traits it lists\n')

// The `inject` line is dropped: the factory's parameter IS the injected ref, and
// keeping the declaration would shadow it.
const detailSrc = between(DETAIL, 'const allTraits = computed(', '// Close self if traitset was deleted')
  .replace(/^const filterQuery = inject\([^\n]*\n/m, '')
const detail = factory(detailSrc, ['traitset', 'filterQuery'],
  '{ allTraits, matchingTraits, traits, filterNote }')

const open = (set, q) => detail({ value: set }, { value: q })

{
  const s = SETS[0]   // Attributes: Might, Grace, Wits
  ok('no query lists every trait', open(s, '').traits.value.map(t => t.name), ['Might', 'Grace', 'Wits'])
  ok('a matching query lists only the matches', open(s, 'gra').traits.value.map(t => t.name), ['Grace'])
  ok('case-insensitive, as the panel is', open(s, 'MIGHT').traits.value.map(t => t.name), ['Might'])
  ok('whitespace is not a query', open(s, '   ').traits.value.map(t => t.name), ['Might', 'Grace', 'Wits'])
  ok('a query matching nothing in the set leaves the set intact',
    open(s, 'zzz').traits.value.map(t => t.name), ['Might', 'Grace', 'Wits'])
}

{
  // The reported bug, in the shape it was reported: one set on screen by its
  // traits, and the traits inside it scoped to what matched.
  const s = SETS[2]   // D4 Tricks: Nimble, Feint
  ok('the set shown for a trait lists that trait, not all of them',
    open(s, 'feint').traits.value.map(t => t.name), ['Feint'])
  ok('…and says how many it is withholding',
    open(s, 'feint').filterNote.value, 'Showing 1 of 2 traits matching “feint”')
}

{
  // A set reached by its NAME must not lose its traits — the trap in the naive
  // fix, where filtering the detail by the same string empties the list.
  const s = MIXED[0]   // Combat Arts: Blade, Bow — neither contains "combat"
  ok('a set reached by its name keeps all its traits',
    open(s, 'combat').traits.value.map(t => t.name), ['Blade', 'Bow'])
  ok('and withholds nothing, so there is no note', open(s, 'combat').filterNote.value, '')
}

{
  const s = SETS[3]   // Empty Set
  ok('a set with no traits lists nothing, query or not', open(s, 'x').traits.value, [])
  ok('and does not claim to be filtering', open(s, 'x').filterNote.value, '')
}

{
  // A query that matches every trait withholds nothing, so there is no note.
  const s = MIXED[0]   // Combat Arts: Blade, Bow
  const view = open(s, 'b')
  ok('a query matching every trait lists them all', view.traits.value.map(t => t.name), ['Blade', 'Bow'])
  ok('…and shows no note, because nothing is withheld', view.filterNote.value, '')
}

// ── 3. the query is live, not a snapshot ─────────────────────────────────
console.log('\nthe query is the parent\'s live ref\n')

{
  // The two panels sit side by side, so the search can be edited with the detail
  // open. A prop copied at open time would freeze it — the stale-prop trap.
  const s = SETS[0]
  const query = { value: '' }
  const view = detail({ value: s }, query)
  ok('starts unfiltered', view.traits.value.length, 3)
  query.value = 'gra'
  ok('editing the query re-scopes the open list', view.traits.value.map(t => t.name), ['Grace'])
  query.value = ''
  ok('clearing it restores every trait', view.traits.value.map(t => t.name), ['Might', 'Grace', 'Wits'])
}

ok('the panel hands over the ref itself, in the spec context',
  /context: \{ traitsetFilter: search \}/.test(PANEL), true)
ok('the detail injects it', /inject\('traitsetFilter', null\)/.test(DETAIL), true)
// The prop route would have to be a snapshot; assert the query is NOT a prop.
ok('the query is not passed as a prop', /props: \{ traitsetId: ts\.id \}/.test(PANEL), true)

// ── 4. the pre-fix shape reproduces the report ───────────────────────────
console.log('\nthe pre-fix detail (all traits, no scoping)\n')

{
  const PRE = 'const traits = computed(() => traitset.value?.traits || [])'
  const preTraits = factory(PRE, ['traitset', 'filterQuery'], 'traits')
  const s = SETS[2]
  ok('it lists a non-matching trait alongside the match',
    preTraits({ value: s }, { value: 'feint' }).value.map(t => t.name), ['Nimble', 'Feint'])
  ok('so it does not equal what the fix lists',
    JSON.stringify(preTraits({ value: s }, { value: 'feint' }).value.map(t => t.name)) !==
    JSON.stringify(open(s, 'feint').traits.value.map(t => t.name)), true)
}

// ── 5. reordering is only offered unfiltered ─────────────────────────────
console.log('\nreordering under a filter\n')

ok('the list is reorderable only with an empty query',
  /:reorderable="!search"/.test(PANEL), true)
ok('and the drag glyph goes with it, so the handle cannot lie',
  /v-if="!search" class="drag-handle"/.test(PANEL), true)

{
  // Why: `reorder_traitsets` numbers the ids it is handed (`order = i + 1`), so a
  // filtered subset would overwrite the front of the global order. Modelled here
  // from the server's own loop.
  const serverOrder = (db, ids) => {
    for (let i = 0; i < ids.length; i++) db[ids[i]] = i + 1
    return db
  }
  const before = { a: 1, b: 2, c: 3, d: 4, e: 5 }
  const shuffled = ['c', 'a']
  const after = serverOrder({ ...before }, shuffled)
  const orders = Object.values(after)
  ok('dragging a 2-of-5 subset collides with the orders it never saw',
    new Set(orders).size < orders.length, true)
  ok('which is why the drag is withheld instead',
    /!search/.test(PANEL), true)
}

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
