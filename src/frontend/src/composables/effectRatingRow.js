/**
 * How a trait-creating effect's **rating** is authored and stored ([[B307]]).
 *
 * A rating is a row of dice, not one die: live content carries 774 instances with
 * more than one, resources up to 16 and challenges usually 3. The row lives in
 * `context.dice` and `result` carries its **first** die, which is what every
 * single-die reader already understands (the handlers' dice parsers, the effect
 * card, the required-field check). Both halves are written together so they cannot
 * drift.
 *
 * Pure and separate from `EffectForm.vue` so the rule can be **executed** by
 * `scripts/check-effect-rating-row.mjs`. The failure this guards is silent: a row
 * the form cannot read is a row it writes back empty, and a gain at no rating
 * looks like a gain that worked.
 */

/** A stored `result` that names a die the author typed, rather than a `{variable}`. */
function isLiteralDie(result) {
  const value = String(result ?? '')
  return !!value && !value.startsWith('{')
}

/**
 * The row as it should appear in the editor: what was stored under `context.dice`,
 * else the legacy single `result` (content authored before the row existed), else
 * nothing. A `{variable}` in `result` means the whole rating is that one named die,
 * so the row stays empty — five live rules take `{effect_die}` that way.
 */
export function ratingRowFor(contextDice, result) {
  if (Array.isArray(contextDice) && contextDice.length) return [...contextDice]
  return isLiteralDie(result) ? [String(result)] : []
}

/**
 * What to store for a given mode. `dice` is `null` when the row does not apply (a
 * named die, or a path), which the caller drops rather than writing `[]`.
 */
export function ratingFieldsFor(mode, row, result) {
  const dice = Array.isArray(row) ? row.filter((d) => !!d) : []
  if (mode !== 'die') return { result: String(result ?? ''), dice: null }
  return { result: dice[0] || '', dice: dice.length ? dice : null }
}
