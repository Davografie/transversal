/**
 * Which `{name}` tokens an effect form offers, and where ([[B306]]).
 *
 * Pure and separate from `EffectForm.vue` so the rule can be **executed** by
 * `scripts/check-effect-variables.mjs`. The frontend has no test runner, and this
 * is exactly the kind of rule a green build cannot see: a picker that offers a
 * name the engine then refuses looks identical to one that works.
 *
 * The defect it fixes: the chips and the die picker read the *activation's* own
 * names only (the trigger's declarations and the source token), so a rule's own
 * **declared** bound variables and an earlier effect's outputs were invisible to
 * both — while every path builder offered them.
 */

// A roll-timed effect's own context names. `{triggered_die_*}` resolves per die
// inside an effect with a die filter (the die *is* the roll there), which is what
// lets an "add a die" granted per unchosen die take its size from that die's tier.
export const ROLL_CONTEXT_VARIABLES = ['effect_die', 'total', 'triggered_die_tier', 'triggered_die_effect_die', 'triggered_die_result', 'triggered_die_die']

// The activation's declared types and the catalog's elements are the same
// vocabulary spelled two ways (`trait_setting` vs `traitsetting`); the backend's
// `element_for_variable` is the mapping, mirrored here for every type a trigger
// or a source kind can carry.
export const VARIABLE_ELEMENTS = {
  die: 'die',
  trait_setting: 'traitsetting',
  traitset_setting: 'traitsetsetting',
  number: 'int',
}

// A die field can only read a **die**: the handler parses the substituted value
// as one. A `rating_die` binding carries its owning trait instance's id rather
// than the die, so it belongs in a *path* (which reads `rating` off it), never
// here; and a `many` binding is never substituted into a `{token}` at all.
export const DIE_ELEMENTS = new Set(['die'])

function normalizeVar(entry) {
  if (!entry) return { element: '', cardinality: 'one' }
  if (typeof entry === 'string') return { element: entry, cardinality: 'one' }
  return { element: entry.element || '', cardinality: entry.cardinality || 'one' }
}

/**
 * Every name in scope for one effect, as `{name: {element, cardinality}}` typed by
 * **catalog element**. `activation` is what the backend reports for the trigger
 * and source kind; `scope` is the typed map the path builders use (declared bound
 * variables, conditions, earlier effects' outputs, this effect's own earlier
 * paths). Where both know a name the typed map wins — it is the answer the engine
 * binds from, cardinality included.
 */
export function scopeEntries(activation = [], scope = {}) {
  const out = {}
  for (const v of (activation || [])) {
    const name = (v && v.name) || (typeof v === 'string' ? v : '')
    if (!name) continue
    out[name] = { element: VARIABLE_ELEMENTS[v?.type] || v?.type || '', cardinality: 'one' }
  }
  for (const [name, t] of Object.entries(scope || {})) {
    const entry = normalizeVar(t)
    if (entry.element) out[name] = entry
  }
  return out
}

/** The names a die field may offer: a die, single, plus the roll context. */
export function dieVariablesFor(entries, rollTiming = false) {
  const out = []
  for (const [name, t] of Object.entries(entries || {})) {
    if (t.cardinality === 'many') continue
    if (DIE_ELEMENTS.has(t.element)) out.push(name)
  }
  if (rollTiming) for (const v of ROLL_CONTEXT_VARIABLES) if (!out.includes(v)) out.push(v)
  return out
}

// What a **rating** may be named by. Wider than `DIE_ELEMENTS`, because an action
// that creates a trait at a whole rating can read a name that *holds* one — the
// engine resolves it into the row (`resolve_effect_dice`) — while an action taking
// a single die can only read a name whose value **is** a die ([[B306]]). The
// caller decides how much of this is usable: `EffectRatingControl` filters by
// whether the action declares a row.
export const RATING_ELEMENTS = new Set(['die', 'rating_die', 'capacity_die'])

/** Rating-capable names with their cardinality, for `EffectRatingControl`. */
export function ratingNamesFor(entries, rollTiming = false) {
  const out = Object.entries(entries || {})
    .filter(([, t]) => RATING_ELEMENTS.has(t.element))
    .map(([name, t]) => ({ name, cardinality: t.cardinality || 'one' }))
  const known = new Set(out.map((v) => v.name))
  if (rollTiming) for (const name of ROLL_CONTEXT_VARIABLES) {
    if (!known.has(name)) out.push({ name, cardinality: 'one' })
  }
  return out
}

/**
 * The chips the author reads: every name in scope, and what it holds. A `many`
 * name is **marked** rather than hidden — it is still readable, but in a *path*
 * (`select variable`), never as a flat `{token}`.
 */
export function chipVariablesFor(entries, rollTiming = false) {
  const out = Object.entries(entries || {}).map(([name, t]) => ({
    name,
    type: t.cardinality === 'many' ? `${t.element} · many` : t.element,
  }))
  if (!rollTiming) return out
  const known = new Set(out.map((v) => v.name))
  for (const name of ROLL_CONTEXT_VARIABLES) if (!known.has(name)) out.push({ name, type: 'roll' })
  return out
}
