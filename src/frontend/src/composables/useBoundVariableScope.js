import { ref, watch } from 'vue'
import { useTargetCatalog } from './useTargetCatalog.js'

/**
 * Resolve one layer of declared bound variables into the scope it produces.
 *
 * A roll table declares names at **two** levels and they resolve in order: the
 * table's, then the chosen row's ([[B281]]). Both layers do the same work — trace
 * each declaration against the scope built so far, then publish its type so a later
 * declaration can start from it — so it lives here rather than being written twice.
 * Two copies of this loop is exactly how the scope the editor *offers* and the scope
 * the engine *binds* drift apart.
 *
 * The trace is the same backend tracer the path builder uses, so what is offered to
 * a later declaration is what `table_bindings()` will actually bind.
 *
 * @param declarations ref/computed of the layer's rows, `{name, spec}`
 * @param base         ref/computed of the scope the layer starts from,
 *                     `{name: {element, cardinality}}`
 * @returns `{ scope, types, refresh }` — the accumulated scope (base + this layer),
 *          each row's resolved type in declaration order (`null` when it resolves
 *          nothing), and a manual refresh
 */
export function useBoundVariableScope(declarations, base) {
  const { traceSpec } = useTargetCatalog()

  const scope = ref({ ...read(base) })
  const types = ref([])

  function read(source) {
    return (source && 'value' in source ? source.value : source) || {}
  }

  async function refresh() {
    const { scope: out, types: resolved } = await resolveLayer(
      read(declarations), read(base), traceSpec)
    scope.value = out
    types.value = resolved
  }

  watch(() => [read(base), read(declarations)], refresh, { immediate: true, deep: true })

  return { scope, types, refresh, read }
}

/** Resolve one layer of declarations against a base scope, in order.
 *
 *  The loop `useBoundVariableScope` runs, exported because a caller may need it for
 *  **several** layers and cannot call a composable in a loop: the life-path panel
 *  resolves a scope for each wrapped table, so a step's effects are offered the
 *  names that table actually declares ([[B281]]), and it resolves the path's and the
 *  step's own layers ahead of it ([[B290]]). One implementation, so what an editor
 *  offers and what `table_bindings()` binds cannot drift.
 *
 *  **A name already in the base wins, and the declaration is refused** — the same
 *  rule the engine applies (`if name in ctx.bindings: continue`), and it has to be
 *  here too: the alternative is an editor offering a name that resolves to the outer
 *  value at run time, which reads as the authored path silently doing nothing. It is
 *  why a table's name beats a row's of the same name, and the first of two in one
 *  list beats the second.
 *
 *  The row's own traced type is still reported in `types` even when refused, so the
 *  editor can show what the author wrote *and* the collision ([[B281]]).
 *
 *  @returns `{scope, types}` — the base plus the names this layer actually binds, and
 *           each row's resolved type in declaration order (`null` when it resolves
 *           nothing)
 */
export async function resolveLayer(declarations, base, traceSpec) {
  const out = { ...(base || {}) }
  const types = []
  for (const row of (declarations || [])) {
    const name = (row?.name || '').trim()
    const steps = row?.spec?.steps || []
    if (!name || !steps.length) { types.push(null); continue }
    let t = null
    try {
      const res = await traceSpec(steps, null, null, out)
      const last = (res?.types || [])[res.types.length - 1]
      if (last?.element && !(res.errors || []).length) {
        t = { element: last.element, cardinality: last.cardinality || 'one' }
      }
    } catch {
      t = null
    }
    types.push(t)
    // An existing name — an ambient fact, an outer layer, or an earlier row — is
    // **not** rebound. The engine refuses it, so offering it would be a lie.
    if (t && !(name in out)) out[name] = t
  }
  return { scope: out, types }
}

/**
 * The **reserved slots** in a declaration layer ([[B285]]).
 *
 * A reservation is a name with a declared type and **no path**: it binds nothing, and
 * it is what every row assigning that name is checked against. One definition, so the
 * slot list an editor offers is the one the engine measures an assignment against —
 * `services/roll_table.is_reservation` is its backend twin, and the two have to agree
 * about what "a slot" is.
 *
 * A declaration with a type *and* a path is not one: it resolves a value, so a row
 * assigning that name is refused as a shadow rather than filled by it.
 *
 * @returns `[{name, element, cardinality}]`, in declaration order
 */
export function reservationsOf(declarations) {
  const out = []
  for (const row of (declarations || [])) {
    const name = (row?.name || '').trim()
    const element = row?.element || ''
    if (!name || !element) continue
    if ((row?.spec?.steps || []).length) continue
    out.push({ name, element, cardinality: row.cardinality || 'one' })
  }
  return out
}
