// Pure, framework-free graph builder for life-path roll-table flowcharts.
//
// A life path is a directed graph of roll tables linked by `next_step` effects.
// This module turns a path + its roll tables into Vue Flow node/edge descriptors
// with a layered (Sugiyama-style, longest-path) auto layout. When several rows
// of one table lead to the same next table, they fan into a small "bundler"
// (reroute) node that then projects a single edge onward.

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

function entryKey(e) {
  if (e.minValue != null || e.maxValue != null) return `${e.minValue ?? ''}–${e.maxValue ?? ''}`
  if (e.weight != null) return `w${e.weight}`
  if (e.tier) return e.tier
  return ''
}

// Collect next_step links: sourceId -> Map(targetId -> {count, labels, rowIndexes})
function collectLinks(tables) {
  const byId = new Map(tables.map((t) => [t.id, t]))
  const links = new Map()

  for (const t of tables) {
    for (let i = 0; i < (t.entries || []).length; i++) {
      const e = t.entries[i]
      for (const eff of e.effects || []) {
        if (eff.type === 'life_path' && eff.action === 'next_step' && eff.target) {
          const target = eff.target
          if (!byId.has(target) || target === t.id) continue
          if (!links.has(t.id)) links.set(t.id, new Map())
          const m = links.get(t.id)
          if (!m.has(target)) m.set(target, { count: 0, labels: [], rowIndexes: [] })
          const g = m.get(target)
          g.count += 1
          g.rowIndexes.push(i)
          g.labels.push(e.label || `entry ${i + 1}`)
        }
      }
    }
  }

  return { byId, links }
}

// DFS from the entry table: mark back-edges (cycles) and the reachable set.
function classify(byId, links, entryId) {
  const adj = new Map()
  for (const [src, m] of links) adj.set(src, [...m.keys()])

  const state = new Map() // 0/undefined = unvisited, 1 = on stack, 2 = done
  const backEdges = new Set()
  const reachable = new Set()

  function dfs(u) {
    state.set(u, 1)
    reachable.add(u)
    for (const v of adj.get(u) || []) {
      if (state.get(v) === 1) {
        backEdges.add(`${u}>${v}`)
      } else if (!state.has(v)) {
        dfs(v)
      }
    }
    state.set(u, 2)
  }

  if (byId.has(entryId)) dfs(entryId)
  return { adj, backEdges, reachable }
}

// Layered longest-path layout over the forward DAG (back-edges excluded).
function computePositions(links, backEdges, reachable) {
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
  for (const id of reachable) indeg.set(id, 0)
  for (const [src, tgts] of fwd) for (const t of tgts) indeg.set(t, (indeg.get(t) || 0) + 1)

  const queue = [...reachable].filter((id) => (indeg.get(id) || 0) === 0).sort()
  const order = []
  while (queue.length) {
    const u = queue.shift()
    order.push(u)
    for (const v of fwd.get(u) || []) {
      indeg.set(v, indeg.get(v) - 1)
      if (indeg.get(v) === 0) queue.push(v)
    }
  }
  // Any node not reached (defensive) keeps insertion order.
  const seen = new Set(order)
  for (const id of reachable) if (!seen.has(id)) order.push(id)

  // Longest-path layer assignment.
  const layer = new Map()
  for (const id of reachable) layer.set(id, 0)
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
// `path`  — { id, name, entryTableId }
// `tables`— RollTable[] (full entries + effects, as returned by GraphQL)
export function buildLifePathGraph(path, tables, opts = {}) {
  const { byId, links } = collectLinks(tables || [])

  if (!path?.entryTableId || !byId.has(path.entryTableId)) {
    return { nodes: [], edges: [] }
  }

  const { backEdges, reachable } = classify(byId, links, path.entryTableId)
  const { positions } = computePositions(links, backEdges, reachable)

  const tableNames = new Map(tables.map((t) => [t.id, t.name]))
  const nodes = []
  const edges = []

  // Tables that belong to this life path (as opposed to out-of-path targets).
  const pathTableIds = new Set()
  for (const t of tables || []) if (t.lifePath === path.id) pathTableIds.add(t.id)

  // True when following next_step links from `id` can reach back into this path.
  function canReachPath(id, seen) {
    seen = seen || new Set()
    if (pathTableIds.has(id)) return true
    if (seen.has(id)) return false
    seen.add(id)
    const targets = links.get(id)
    if (!targets) return false
    for (const tgt of targets.keys()) {
      if (canReachPath(tgt, seen)) return true
    }
    return false
  }

  for (const id of reachable) {
    const t = byId.get(id)
    // Prefer a persisted GM arrangement over the auto-computed DAG position.
    const saved = (t.canvasX != null && t.canvasY != null) ? { x: t.canvasX, y: t.canvasY } : null
    const pos = saved || positions.get(id) || { x: 0, y: 0 }

    // Row-level view with the first next_step target resolved for a badge.
    const rows = (t.entries || []).map((e, i) => {
      let nextTarget = null
      for (const eff of e.effects || []) {
        if (eff.type === 'life_path' && eff.action === 'next_step' && eff.target && byId.has(eff.target) && eff.target !== id) {
          nextTarget = { id: eff.target, name: tableNames.get(eff.target) || eff.target }
          break
        }
      }
      return {
        index: i,
        label: e.label || '',
        description: e.description || '',
        key: entryKey(e),
        effects: e.effects || [],
        conditions: e.conditions || [],
        nextTarget,
      }
    })

    const external = t.lifePath !== path.id
    const pathMeta = opts.pathMeta || {}
    const meta = pathMeta[t.lifePath] || {}

    nodes.push({
      id: `rt:${id}`,
      type: 'rolltable',
      position: pos,
      data: {
        entityId: id,
        name: t.name,
        universe: t.universe,
        scheme: t.scheme,
        die: t.die,
        rollSource: t.rollSource,
        tableNames: Object.fromEntries(tableNames),
        lifePathName: meta.name || '',
        factionNames: meta.factionNames || [],
        external,
        terminal: external && !canReachPath(id),
        rows,
      },
    })

    // Outgoing edges. Groups with one entry connect directly; groups with
    // several entries fan through a bundler (reroute) node.
    const m = links.get(id)
    if (!m) continue

    for (const [tgt, g] of m) {
      const isBack = backEdges.has(`${id}>${tgt}`)

      if (g.count > 1) {
        const bundlerId = `bd:${id}:${tgt}`
        const first = g.rowIndexes[0]
        const last = g.rowIndexes[g.rowIndexes.length - 1]
        const centerRow = (first + last) / 2
        const rowCenterY = pos.y + RT_HEADER_H + RT_SUBTITLE_H + RT_META_H + centerRow * RT_ROW_H + RT_ROW_H / 2

        nodes.push({
          id: bundlerId,
          type: 'bundler',
          position: { x: pos.x + RT_WIDTH + BD_GAP, y: rowCenterY - BD_SIZE / 2 },
          draggable: false,
          data: { count: g.count, labels: g.labels, parentId: id },
        })

        // Fan-in: one wire per row into the bundler.
        for (const ri of g.rowIndexes) {
          edges.push({
            id: `lp:${id}:${tgt}:r${ri}`,
            source: `rt:${id}`,
            sourceHandle: `row-${ri}`,
            target: bundlerId,
            targetHandle: 'in',
            type: 'default',
            data: { kind: 'bundle' },
          })
        }

        // Bundler projects a single edge to the target table.
        edges.push({
          id: `lp:${id}:${tgt}:out`,
          source: bundlerId,
          sourceHandle: 'out',
          target: `rt:${tgt}`,
          targetHandle: 'target',
          type: 'lifepath',
          label: `${g.count} entries`,
          data: { kind: isBack ? 'back' : 'forward', count: g.count, labels: g.labels },
        })
      } else {
        edges.push({
          id: `lp:${id}:${tgt}`,
          source: `rt:${id}`,
          sourceHandle: `row-${g.rowIndexes[0]}`,
          target: `rt:${tgt}`,
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
