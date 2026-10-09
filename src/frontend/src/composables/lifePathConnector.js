// Pure helpers for the roll-table editor's life-path **connector** column.
//
// A binding carries four meanings, and the select shows one token for all four:
// no binding at all (`follow`), a step id it moves to, an `exitKind`
// (`muster` / `force_muster` / `draft`), or a binding with neither (the term
// simply ends). Kept out of the SFC so the mapping runs under plain node — the
// frontend has no test runner (see tests/lifePathGraph.steps.mjs).

export const CONNECTOR_FOLLOW = 'follow'
export const CONNECTOR_END = 'end'

// A row's stable identity. Must match `row_key()` in the API
// (src/api/src/transversal/services/roll_table.py) **exactly** — the range
// separator is an en-dash (U+2013) — or a displayed key and a stored binding key
// would disagree.
export function rowKey(entry, index = 0) {
  if (entry?.key) return entry.key
  if (entry?.minValue != null || entry?.maxValue != null) {
    return `${entry.minValue ?? ''}\u2013${entry.maxValue ?? ''}`
  }
  if (entry?.weight != null) return `w${entry.weight}`
  if (entry?.tier) return String(entry.tier)
  return String(index)
}

// The select's value: one token for the four meanings.
export function connectorToken(binding) {
  if (!binding) return CONNECTOR_FOLLOW
  if (binding.next) return binding.next
  if (binding.exitKind) return binding.exitKind
  return CONNECTOR_END
}

// The destination in words, for the read-back line beside the select.
// `stepById` maps a step id to its step (for the label); `pathNameOf` maps a
// draft destination id to a life-path name.
export function connectorText(binding, { stepById, pathNameOf } = {}) {
  if (!binding) return 'Follows the step'
  if (binding.next) {
    const step = stepById?.get(binding.next)
    return step ? (step.label || step.id) : binding.next
  }
  switch (binding.exitKind) {
    case 'muster': return 'Muster out'
    case 'force_muster': return 'Muster out (dishonourably)'
    case 'draft': {
      const name = pathNameOf ? pathNameOf(binding.exitPath) : ''
      return name ? `Draft to ${name}` : 'Draft to another path'
    }
    default: return 'Ends the term'
  }
}
