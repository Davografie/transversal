/**
 * A roll-table **menu** rule: which table it opens, and when.
 *
 * A `roll_table/menu` effect is a *client* action — it has no applier, so the
 * backend passes it straight through and the sheet is the only actor. That is why
 * the table id has to be knowable on the client, and why the client's rule for
 * finding it is worth one definition.
 *
 * The table is a **reference** (`refs.table`) since the named-refs migration: a
 * literal one names the table outright, and a *path* one (`select roll_tables →
 * choose`) names it as a question — so the click cannot open the menu and the
 * **answer** does. Reading the superseded positional `target` instead is what
 * stopped every menu rule opening at all: the migration emptied it, and a menu
 * effect that cannot name its table opens nothing and says nothing.
 */

/** The menu effect a rule carries, or `null` when it is not a menu rule. */
export function rollTableMenuEffect(sfx) {
  return (sfx?.effects || []).find((e) => e.type === 'roll_table' && e.action === 'menu') || null
}

/** The table a menu effect names outright (its `refs.table` value, else the
 *  legacy positional `target`) — `''` when the reference is a path, i.e. when the
 *  table is named by a question rather than by the rule. */
export function rollTableIdOf(effect) {
  if (!effect) return ''
  return effect.refs?.table?.value || effect.target || ''
}

/** The table an **answered** reference path names, or `''` when this answer is
 *  not the one that names it.
 *
 * Only a fully-answered path counts: an earlier `choose` in the same path (a
 * universe, a region) arrives as its own answer, and opening the menu on that
 * would open the wrong table — or none.
 */
export function rollTableIdFromAnswer(resolution) {
  const effect = resolution?.effect
  if (!effect || effect.type !== 'roll_table' || effect.action !== 'menu') return ''

  const field = String(resolution.field || '')
  const refName = field.startsWith('refs.') ? field.slice('refs.'.length) : ''
  const steps = refName ? (effect.refs?.[refName]?.spec?.steps || []) : []
  const answers = resolution.answers || []
  if (!steps.length || !answers.length) return ''

  const last = answers[answers.length - 1]
  if (last?.stepIndex !== steps.length - 1) return ''
  return last.ids?.[0] || ''
}
