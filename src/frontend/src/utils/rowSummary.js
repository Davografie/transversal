// The choice table's row vocabulary, as pure functions.
//
// A row can carry a roll key, a cost, gating conditions and effects — and every
// one of those can name a domain id. Phrasing them is therefore *one* job with
// *one* resolver, not a job each host re-implements: the life-path wizard used
// to render `trait-rel-tenure` raw whenever the path's universe didn't stamp the
// trait, and the canvas node rendered every trait target as raw text, because
// each host carried its own name map. These helpers take the resolver as an
// argument so there is exactly one phrasing and it cannot drift per host.
//
// See [[UI-UX Design#Choice table]].

/** Comparators read as symbols in a phrase; `>=` on screen is noise. */
const OPERATORS = { '>=': '≥', '<=': '≤', '==': '=', '!=': '≠', '>': '>', '<': '<' }

function operator(op) {
  return OPERATORS[op] || op || ''
}

/**
 * A human label for an id, via `resolve`. An unresolved id stays as it is —
 * the *resolver* owns the "what if it is unknown" decision (see
 * `useLabelResolver`), so a caller can never silently invent a different one.
 */
function named(id, resolve) {
  if (id === null || id === undefined || id === '') return ''
  return (resolve ? resolve(id) : id) || id
}

function list(ids, resolve) {
  return (ids || []).map((v) => named(v, resolve)).filter(Boolean).join(' or ')
}

/**
 * The row's leading cell. **A row's key means a different thing per scheme**, so
 * the key column is derived from the table's scheme and never stored on the row:
 *
 *   RANGE  → `min–max`   INDEX → the position   TIER → the tier   WEIGHT → `w`
 *
 * A scheme the row does not match (or no scheme at all) falls back to whatever
 * the row actually carries, then to its position — so an authoring list and a
 * runtime list can share one renderer without either lying about the key.
 */
export function entryKey(entry, index, scheme) {
  const e = entry || {}
  const range = (e.minValue != null || e.maxValue != null)
    ? `${e.minValue ?? ''}–${e.maxValue ?? ''}`
    : ''
  const s = String(scheme || '').toUpperCase()

  if (s === 'RANGE') return range || String(index + 1)
  if (s === 'WEIGHT') return e.weight ? `w${e.weight}` : String(index + 1)
  if (s === 'TIER') return e.tier || String(index + 1)
  if (s === 'INDEX') return String(index + 1)

  // No scheme (or an unknown one): read the row.
  if (e.tier) return e.tier
  if (e.weight) return `w${e.weight}`
  if (range) return range
  return String(index + 1)
}

/**
 * One condition as a phrase a player can read: `has Tenure`, `razmerit ≥ 3`,
 * `in Three Realms`. A `narrative` is the author's own words and wins when the
 * type carries no structure of its own (or none we recognise).
 */
export function conditionSummary(c, resolve) {
  if (c === null || c === undefined) return ''
  if (typeof c === 'string') return c
  if (c.phrase) return c.phrase          // a server-supplied human phrase (B179/B193)

  const type = String(c.type || '').toLowerCase()
  const target = named(c.target, resolve)
  const subjects = list(c.targets, resolve) || target
  const subject = named(c.subject, resolve)
  // An enum filter accepts one value (`target`) or several (`targets`, any-of),
  // and a phrase has to read the same either way.
  const value = c.value === null || c.value === undefined || c.value === '' ? '' : String(c.value)
  const op = operator(c.operator)
  const cmp = [op, value].filter(Boolean).join(' ')
  const who = subjects || target

  switch (type) {
    case '': return c.narrative || ''
    case 'always': return 'always'
    case 'at_location': return who ? `at ${who}` : 'at a location'
    case 'has_trait': return who ? `has ${who}` : 'has a trait'
    case 'has_effective_trait': return who ? `has ${who} enabled` : 'has a trait enabled'
    case 'has_trait_in_traitset': return who ? `has a ${who} trait` : 'has a trait from a set'
    case 'has_relationship': return who ? `has a tie to ${who}` : 'has a tie'
    case 'trait_rating': return [who || 'rating', cmp].filter(Boolean).join(' ')
    case 'has_razmerit': return `razmerit ${cmp}`.trim()
    case 'entity_type': return subject ? `${subject} is ${who || 'of a type'}` : `${who || 'entity'}`
    case 'user_role': return who ? `acting as ${who}` : 'acting as a role'
    case 'narrative': return c.narrative || subjects || 'a narrative condition'
    case 'unplaced': return 'has no location yet'
    case 'in_universe': return who ? `in ${who}` : 'in a universe'
    case 'phase': return who ? `phase ${who}` : 'in a phase'
    case 'contest_outcome': return who ? `contest ${who}` : 'a contest outcome'
    case 'hitch': return 'the hitch menu is open'
    case 'roll_tier': return `tier ${cmp}`.trim()
    case 'test_outcome': return who ? `test ${who}` : 'a test outcome'
    case 'source_rating': return `source rating ${cmp}`.trim()
    case 'high_stakes': return who ? `${who} stakes` : 'high stakes'
    case 'target_path': return 'a targeting path resolves'
    case 'arrival_kind': return who ? `arrived by ${who}` : 'a way of arriving'
    case 'contest_challenger': return 'declared the contest'
    case 'contest_defendant': return 'was challenged'
    case 'session': return who ? `session ${who}` : 'a session state'
    default: return c.narrative || [type.replace(/_/g, ' '), who, cmp].filter(Boolean).join(' ')
  }
}

/**
 * One effect as a phrase. `labelFor` is the action catalog's own label
 * (`useEffectActions().labelFor`); without it the raw `type/action` pair is the
 * most honest thing we can say, and it is the *one* place that fallback lives.
 */
export function effectSummary(effect, { labelFor, resolve } = {}) {
  if (!effect) return ''
  if (typeof effect === 'string') return effect

  const label = (labelFor && labelFor(effect)) || [effect.type, effect.action].filter(Boolean).join('/')
  const target = named(effect.target, resolve)
  const parts = [label]
  if (target && target !== 'self' && target !== '{source_trait}') parts.push(`→ ${target}`)
  if (effect.result) parts.push(`(${effect.result})`)
  if (effect.duration) parts.push('· lasting')
  return parts.filter(Boolean).join(' ')
}

/** The cost cell: razmerit first (it is the price players compare), then the rest. */
export function costSummary(costEffects, summarize) {
  const costs = costEffects || []
  const raz = costs.reduce((sum, e) => {
    if (e && e.type === 'transfer_razmerit' && e.action === 'spend') {
      return sum + (parseInt(e.result, 10) || 0)
    }
    return sum
  }, 0)
  const rest = costs.filter((e) => !(e && e.type === 'transfer_razmerit' && e.action === 'spend'))
  const parts = []
  if (raz > 0) parts.push(`${raz} razmerit`)
  if (rest.length) parts.push(rest.map((e) => (summarize ? summarize(e) : '')).filter(Boolean).join(', '))
  return { label: parts.filter(Boolean).join(' · '), razmerit: raz, free: parts.filter(Boolean).length === 0 }
}
