// Pure, framework-free graph builder for life-path roll-table flowcharts.
//
// A life path **wraps** roll tables: `path.steps` names each wrapped table at a
// position in the path, and a step's `bindings` say what one row of that table
// means to *this* path (advance to a step, or leave the path). This module turns
// a path + its roll tables into Vue Flow node/edge descriptors with a layered
// (Sugiyama-style, longest-path) auto layout. When several rows of one step lead
// to the same next step, they fan into a small "bundler" (reroute) node that then
// projects a single edge onward.
//
// Nodes are keyed by **step id** (`step:<stepId>`), never by table id: a path may
// wrap the same table at two steps, and a table id is not unique within a path.

export const LP_DX = 300 // horizontal spacing between columns
export const LP_DY = 340 // vertical spacing between layers

// Node metrics shared with RollTableNode.vue so bundler positions align with
// the table's entry rows.
export const RT_WIDTH = 250
export const RT_HEADER_H = 40
export const RT_SUBTITLE_H = 16
export const RT_META_H = 20
export const RT_ROW_H = 26

export const BD_GAP = 56 // horizontal gap from a table's right edge to its bundlers
export const BD_SIZE = 18 // bundler node diameter

// A row's stable identity. Rows carry an authored `key` now; the fallback derives
// one from the band. It must match `row_key()` in the API
// (src/api/src/transversal/services/roll_table.py) **exactly** — the range
// separator is an en-dash (U+2013) — or a displayed key and a stored binding key
// would disagree.
function entryKey(e, index = 0) {
  if (e.key) return e.key
  if (e.minValue != null || e.maxValue != null) return `${e.minValue ?? ''}–${e.maxValue ?? ''}`
  if (e.weight != null) return `w${e.weight}`
  if (e.tier) return String(e.tier)
  return String(index)
}

// A resolved step destination, as a row badge shows it: the wrapped table's name,
// plus the path's own label for the step.
function stepTarget(id, stepById, nameOfTable) {
  const step = stepById.get(id)
  if (!step) return null
  return { id, name: nameOfTable(step.tableId) || step.tableId, label: step.label || '' }
}

// Where one row goes: a step (an edge), an exit (a terminal with a kind), or
// nowhere (the term simply ends). A binding that names the row wins over the
// step's default `next`; a row with no binding of its own follows the default.
function resolveRow(step, entry, index, stepById, nameOfTable) {
  const key = entryKey(entry, index)
  const binding = (step.bindings || []).find((b) => (b.key || '') === key) || null
  const exitKind = binding ? (binding.exitKind || '') : ''
  const next = binding ? (binding.next || '') : (step.next || '')
  return {
    key,
    binding,
    via: binding ? 'binding' : 'default',
    // An exit is a destination with a kind, not an edge to a node.
    exit: exitKind ? { kind: exitKind, path: (binding.exitPath || '') } : null,
    nextTarget: !exitKind && next && stepById.has(next)
      ? stepTarget(next, stepById, nameOfTable)
      : null,
  }
}

// Collect step -> step links: sourceStepId -> Map(targetStepId -> {count, labels, rowIndexes}).
// Destinations are resolved row by row, so a row that exits the path is not a link.
function collectLinks(steps, stepById, tableById, nameOfTable) {
  const links = new Map()
  const rowsByStep = new Map()

  for (const step of steps) {
    const table = tableById.get(step.tableId)
    const rows = []

    for (let i = 0; i < (table.entries || []).length; i++) {
      const entry = table.entries[i]
      const r = resolveRow(step, entry, i, stepById, nameOfTable)
      rows.push({ ...r, index: i, entry })
      if (!r.nextTarget) continue

      if (!links.has(step.id)) links.set(step.id, new Map())
      const m = links.get(step.id)
      const tgt = r.nextTarget.id
      if (!m.has(tgt)) m.set(tgt, { count: 0, labels: [], rowIndexes: [] })
      const g = m.get(tgt)
      g.count += 1
      g.rowIndexes.push(i)
      g.labels.push(entry.label || `entry ${i + 1}`)
    }

    rowsByStep.set(step.id, rows)
  }

  return { links, rowsByStep }
}

// DFS from the entry step: mark back-edges (cycles) so the layout can ignore them.
function classify(links, entryId) {
  const adj = new Map()
  for (const [src, m] of links) adj.set(src, [...m.keys()])

  const state = new Map() // 0/undefined = unvisited, 1 = on stack, 2 = done
  const backEdges = new Set()

  function dfs(u) {
    state.set(u, 1)
    for (const v of adj.get(u) || []) {
      if (state.get(v) === 1) {
        backEdges.add(`${u}>${v}`)
      } else if (!state.has(v)) {
        dfs(v)
      }
    }
    state.set(u, 2)
  }

  if (entryId) dfs(entryId)
  return { backEdges }
}

// Layered longest-path layout over the forward DAG (back-edges excluded).
function computePositions(links, backEdges, nodeIds) {
  const fwd = new Map() // node -> forward children
  const parent = new Map() // node -> forward parents
  for (const [src, m] of links) {
    for (const tgt of m.keys()) {
      if (backEdges.has(`${src}>${tgt}`)) continue
      if (!fwd.has(src)) fwd.set(src, [])
      fwd.get(src).push(tgt)
      if (!parent.has(tgt)) parent.set(tgt, [])
      parent.get(tgt).push(src)
    }
  }

  // Kahn topological sort (deterministic).
  const indeg = new Map()
  for (const id of nodeIds) indeg.set(id, 0)
  for (const [src, tgts] of fwd) for (const t of tgts) indeg.set(t, (indeg.get(t) || 0) + 1)

  const queue = [...nodeIds].filter((id) => (indeg.get(id) || 0) === 0).sort()
  const order = []
  while (queue.length) {
    const u = queue.shift()
    order.push(u)
    for (const v of fwd.get(u) || []) {
      indeg.set(v, indeg.get(v) - 1)
      if (indeg.get(v) === 0) queue.push(v)
    }
  }
  // Any node not reached (defensive: a cycle not rooted at the entry) keeps insertion order.
  const seen = new Set(order)
  for (const id of nodeIds) if (!seen.has(id)) order.push(id)

  // Longest-path layer assignment.
  const layer = new Map()
  for (const id of nodeIds) layer.set(id, 0)
  for (const u of order) {
    for (const v of fwd.get(u) || []) {
      layer.set(v, Math.max(layer.get(v), layer.get(u) + 1))
    }
  }

  // Group by layer, then refine ordering with two barycenter passes.
  const maxLayer = Math.max(0, ...[...layer.values()])
  const layerIds = []
  for (let l = 0; l <= maxLayer; l++) layerIds[l] = []
  for (const u of order) layerIds[layer.get(u)].push(u)

  for (let pass = 0; pass < 2; pass++) {
    const idx = new Map()
    layerIds.forEach((ids) => ids.forEach((id, i) => idx.set(id, i)))
    for (let l = 1; l <= maxLayer; l++) {
      layerIds[l].sort((a, b) => {
        const avg = (id) => {
          const ps = parent.get(id) || []
          if (!ps.length) return idx.get(id) ?? 0
          return ps.reduce((s, p) => s + (idx.get(p) ?? 0), 0) / ps.length
        }
        return avg(a) - avg(b)
      })
    }
  }

  const positions = new Map()
  layerIds.forEach((ids, l) => {
    ids.forEach((id, i) => {
      positions.set(id, { x: (i - (ids.length - 1) / 2) * LP_DX, y: l * LP_DY })
    })
  })

  return { positions }
}

// Build Vue Flow node/edge descriptors for one life path.
//
// `path`  — { id, name, entryStep, steps: [{ id, tableId, label, next, bindings }] }
// `tables`— RollTable[] (full entries + keys, as returned by GraphQL)
export function buildLifePathGraph(path, tables, opts = {}) {
  const tableById = new Map((tables || []).map((t) => [t.id, t]))
  const tableNames = new Map((tables || []).map((t) => [t.id, t.name]))
  const nameOfTable = (id) => tableNames.get(id) || id

  // `path.steps` is the authoritative node set. A step is drawable only when the
  // table it wraps is present.
  const steps = (path?.steps || []).filter((s) => s?.id && tableById.has(s.tableId))
  const stepById = new Map(steps.map((s) => [s.id, s]))

  if (!path?.entryStep || !stepById.has(path.entryStep)) {
    return { nodes: [], edges: [] }
  }

  const { links, rowsByStep } = collectLinks(steps, stepById, tableById, nameOfTable)
  const { backEdges } = classify(links, path.entryStep)
  const { positions } = computePositions(links, backEdges, new Set(steps.map((s) => s.id)))

  const pathMeta = opts.pathMeta || {}
  const meta = pathMeta[path.id] || {}
  const nodes = []
  const edges = []

  // Persisted canvasX/canvasY live on the *table*, so two steps wrapping the same
  // table would otherwise land exactly on top of each other: the n-th occurrence
  // of a table is nudged along x.
  const occurrence = new Map()

  for (const step of steps) {
    const t = tableById.get(step.tableId)
    const occ = occurrence.get(t.id) || 0
    occurrence.set(t.id, occ + 1)

    // Prefer a persisted GM arrangement over the auto-computed DAG position.
    const saved = (t.canvasX != null && t.canvasY != null)
      ? { x: t.canvasX + occ * LP_DX, y: t.canvasY }
      : null
    const pos = saved || positions.get(step.id) || { x: 0, y: 0 }

    const rows = (rowsByStep.get(step.id) || []).map((r) => ({
      index: r.index,
      key: r.key,
      label: r.entry.label || '',
      description: r.entry.description || '',
      effects: r.entry.effects || [],
      conditions: r.entry.conditions || [],
      // The path's own overlay for this row, applied after the row's effects.
      bindingEffects: (r.binding && r.binding.effects) || [],
      nextTarget: r.nextTarget,
      exit: r.exit,
      via: r.via,
      enroll: !!(r.binding && r.binding.enroll),
    }))

    nodes.push({
      id: `step:${step.id}`,
      type: 'rolltable',
      position: pos,
      data: {
        stepId: step.id,
        entityId: t.id,
        tableId: t.id,
        name: t.name,
        stepLabel: step.label || '',
        universe: t.universe,
        scheme: t.scheme,
        die: t.die,
        rollSource: t.rollSource,
        tableNames: Object.fromEntries(tableNames),
        lifePathName: meta.name || '',
        factionNames: meta.factionNames || [],
        // The path declares its own steps, so an edge never leaves the path:
        // every drawn node is internal. Kept for RollTableNode's styling hooks.
        external: false,
        terminal: false,
        // The step's default destination, for rows with no binding of their own.
        defaultNext: step.next && stepById.has(step.next)
          ? stepTarget(step.next, stepById, nameOfTable)
          : null,
        rows,
      },
    })

    // Outgoing edges. Groups with one row connect directly; groups with several
    // rows fan through a bundler (reroute) node keyed to this step.
    const m = links.get(step.id)
    if (!m) continue

    for (const [tgt, g] of m) {
      const isBack = backEdges.has(`${step.id}>${tgt}`)

      if (g.count > 1) {
        const bundlerId = `bd:${step.id}:${tgt}`
        const first = g.rowIndexes[0]
        const last = g.rowIndexes[g.rowIndexes.length - 1]
        const centerRow = (first + last) / 2
        const rowCenterY = pos.y + RT_HEADER_H + RT_SUBTITLE_H + RT_META_H + centerRow * RT_ROW_H + RT_ROW_H / 2

        nodes.push({
          id: bundlerId,
          type: 'bundler',
          position: { x: pos.x + RT_WIDTH + BD_GAP, y: rowCenterY - BD_SIZE / 2 },
          draggable: false,
          data: { count: g.count, labels: g.labels, parentId: step.id },
        })

        // Fan-in: one wire per row into the bundler.
        for (const ri of g.rowIndexes) {
          edges.push({
            id: `lp:${step.id}:${tgt}:r${ri}`,
            source: `step:${step.id}`,
            sourceHandle: `row-${ri}`,
            target: bundlerId,
            targetHandle: 'in',
            type: 'default',
            data: { kind: 'bundle' },
          })
        }

        // Bundler projects a single edge to the target step.
        edges.push({
          id: `lp:${step.id}:${tgt}:out`,
          source: bundlerId,
          sourceHandle: 'out',
          target: `step:${tgt}`,
          targetHandle: 'target',
          type: 'lifepath',
          label: `${g.count} entries`,
          data: { kind: isBack ? 'back' : 'forward', count: g.count, labels: g.labels },
        })
      } else {
        edges.push({
          id: `lp:${step.id}:${tgt}`,
          source: `step:${step.id}`,
          sourceHandle: `row-${g.rowIndexes[0]}`,
          target: `step:${tgt}`,
          targetHandle: 'target',
          type: 'lifepath',
          label: g.labels[0],
          data: { kind: isBack ? 'back' : 'forward', count: 1, labels: g.labels },
        })
      }
    }
  }

  return { nodes, edges }
}
