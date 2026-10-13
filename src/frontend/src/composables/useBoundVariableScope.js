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
    const start = { ...read(base) }
    const out = { ...start }
    const resolved = []
    for (const row of (read(declarations) || [])) {
      const name = (row?.name || '').trim()
      const steps = row?.spec?.steps || []
      if (!name || !steps.length) { resolved.push(null); continue }
      try {
        const res = await traceSpec(steps, null, null, out)
        const last = (res?.types || [])[res.types.length - 1]
        if (last?.element && !(res.errors || []).length) {
          const t = { element: last.element, cardinality: last.cardinality || 'one' }
          resolved.push(t)
          out[name] = t
        } else {
          resolved.push(null)
        }
      } catch {
        resolved.push(null)
      }
    }
    scope.value = out
    types.value = resolved
  }

  watch(() => [read(base), read(declarations)], refresh, { immediate: true, deep: true })

  return { scope, types, refresh, read }
}
