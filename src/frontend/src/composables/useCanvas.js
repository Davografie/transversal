import { ref, computed } from 'vue'

const API_BASE = '/api/v1'

// Module-level singleton state — shared across all canvas instances.
const nodes = ref([])
const edges = ref([])
const mode = ref('location') // 'location' | 'faction' | 'gmc-web'
const focusId = ref(null)
const title = ref('')
const loading = ref(false)
const error = ref(null)

// Persistent knowledge of what the canvas has loaded, keyed by entity id.
// Lets expand/collapse lazily add nodes without refetching already-known ones.
const entityCache = new Map()
const factions = ref([])

// ── Node/edge factories ───────────────────────────────

function nodeId(kind, id) {
  return `${kind}:${id}`
}

function makeLocationNode(entity, opts = {}) {
  const id = nodeId('loc', entity._key || entity.id)
  entityCache.set(id, { kind: 'location', ...entity })
  return {
    id,
    type: 'location',
    position: { x: 0, y: 0 },
    data: {
      entityId: entity._key || entity.id,
      name: entity.name,
      universe: entity.current_universe,
      isFocus: !!opts.isFocus,
      expanded: !!opts.expanded,
      isScaffolding: !!opts.isScaffolding,
    },
  }
}

function makeOccupantNode(entity, opts = {}) {
  const id = nodeId('occ', entity.id)
  entityCache.set(id, { kind: 'occupant', ...entity })
  return {
    id,
    type: 'occupant',
    position: { x: 0, y: 0 },
    data: {
      entityId: entity.id,
      name: entity.name,
      entityType: entity.type,
      image: entity.image || null,
      locationId: entity.location_id || entity.current_location || null,
      factions: opts.factions || [],
      rank: opts.rank || null,
      role: opts.role || null,
    },
  }
}

// ── Layout constants ──────────────────────────────────

const DX = 240
const DY = 140

// ── Public API ────────────────────────────────────────

export function useCanvas() {
  async function loadLocation(locationId) {
    loading.value = true
    error.value = null
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/canvas`)
      if (!r.ok) throw new Error(await r.text())
      const data = await r.json()
      if (!data.location) throw new Error('Location not found')
      mode.value = 'location'
      focusId.value = locationId
      title.value = data.location.name
      buildLocationGraph(data)
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function loadFaction(factionId) {
    loading.value = true
    error.value = null
    try {
      const r = await fetch(`${API_BASE}/factions/${factionId}/canvas`)
      if (!r.ok) throw new Error(await r.text())
      const data = await r.json()
      if (!data.faction) throw new Error('Faction not found')
      mode.value = 'faction'
      focusId.value = factionId
      title.value = data.faction.name
      buildFactionGraph(data)
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function loadGmcWeb(gmcId) {
    loading.value = true
    error.value = null
    try {
      const r = await fetch(`${API_BASE}/gmcs/${gmcId}/web`)
      if (!r.ok) throw new Error(await r.text())
      const data = await r.json()
      if (!data.gmc) throw new Error('GMC not found')
      mode.value = 'gmc-web'
      focusId.value = gmcId
      title.value = data.gmc.name
      buildGmcWebGraph(data)
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function expandLocation(locationId) {
    loading.value = true
    error.value = null
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/canvas`)
      if (!r.ok) throw new Error(await r.text())
      const data = await r.json()
      if (!data.location) throw new Error('Location not found')
      mergeLocationGraph(data, locationId)
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  function clear() {
    nodes.value = []
    edges.value = []
    entityCache.clear()
    focusId.value = null
    title.value = ''
    error.value = null
  }

  // ── Graph builders ─────────────────────────────────

  function buildLocationGraph(data) {
    const newNodes = []
    const newEdges = []

    const focus = makeLocationNode(data.location, { isFocus: true, expanded: true })
    newNodes.push(focus)

    // Parent (above) + super edge
    if (data.parent) {
      const parent = makeLocationNode(data.parent, { expanded: false })
      newNodes.push(parent)
      newEdges.push(makeSuperEdge(focus.id, parent.id))
    }

    // Children (below) + super edges
    for (const child of data.children || []) {
      const c = makeLocationNode(child, { expanded: false })
      newNodes.push(c)
      newEdges.push(makeSuperEdge(c.id, focus.id))
    }

    // Transversal peers (lateral) + transversal edges
    for (const peer of data.transversal || []) {
      const p = makeLocationNode(peer, { expanded: false })
      newNodes.push(p)
      newEdges.push(makeTransversalEdge(focus.id, p.id))
    }

    // Occupants at the focus location
    const memberships = data.faction_memberships || {}
    for (const occ of data.occupants || []) {
      const o = makeOccupantNode(occ, { factions: memberships[occ.id] || [] })
      newNodes.push(o)
      newEdges.push(makeLocatedEdge(focus.id, o.id))
    }

    // Occupant-to-occupant relations (visible in faction mode / on toggle)
    for (const rel of data.occupant_relations || []) {
      newEdges.push(makeRelationEdge(nodeId('occ', rel.from), nodeId('occ', rel.to), rel.description))
    }

    nodes.value = newNodes
    edges.value = newEdges
    layoutLocationNodes()
  }

  function mergeLocationGraph(data, expandedId) {
    // Add newly expanded location's neighborhood to the existing graph.
    const existingIds = new Set(nodes.value.map((n) => n.id))
    const newNodes = []
    const newEdges = []

    const expandedLocId = nodeId('loc', data.location._key || data.location.id)

    if (data.parent && !existingIds.has(nodeId('loc', data.parent._key))) {
      const p = makeLocationNode(data.parent, { expanded: false })
      newNodes.push(p)
      newEdges.push(makeSuperEdge(expandedLocId, p.id))
    }
    for (const child of data.children || []) {
      const cid = nodeId('loc', child._key || child.id)
      if (!existingIds.has(cid)) {
        const c = makeLocationNode(child, { expanded: false })
        newNodes.push(c)
        newEdges.push(makeSuperEdge(c.id, expandedLocId))
      }
    }
    for (const peer of data.transversal || []) {
      const pid = nodeId('loc', peer._key || peer.id)
      if (!existingIds.has(pid)) {
        const p = makeLocationNode(peer, { expanded: false })
        newNodes.push(p)
        newEdges.push(makeTransversalEdge(expandedLocId, p.id))
      }
    }
    const memberships = data.faction_memberships || {}
    for (const occ of data.occupants || []) {
      const oid = nodeId('occ', occ.id)
      if (!existingIds.has(oid)) {
        const o = makeOccupantNode(occ, { factions: memberships[occ.id] || [] })
        newNodes.push(o)
        newEdges.push(makeLocatedEdge(expandedLocId, o.id))
      }
    }

    nodes.value = [...nodes.value, ...newNodes]
    edges.value = [...edges.value, ...newEdges]

    // Mark the expanded node as expanded
    const target = nodes.value.find((n) => n.id === expandedLocId)
    if (target) target.data.expanded = true

    layoutLocationNodes()
  }

  function buildFactionGraph(data) {
    const newNodes = []
    const newEdges = []

    const memberNodes = data.members || []
    // Locations where members live + ancestor scaffolding
    const locById = new Map()
    for (const loc of data.locations || []) {
      locById.set(loc.id, { ...loc, scaffolding: false })
    }
    for (const loc of data.ancestors || []) {
      if (!locById.has(loc.id)) locById.set(loc.id, { ...loc, scaffolding: true })
    }

    // Build a location tree from scaffolding + member locations.
    // We approximate the tree by nesting member locations under their
    // ancestors, but for simplicity we render a flat forest of locations.
    for (const [id, loc] of locById) {
      newNodes.push(makeLocationNode({ _key: id, name: loc.name, current_universe: loc.universe }, { isScaffolding: loc.scaffolding, expanded: false }))
    }

    // Members as occupant nodes under their location.
    for (const m of memberNodes) {
      const o = makeOccupantNode({ id: m.id, name: m.name, type: 'gmc', location_id: m.location_id }, { rank: m.rank, role: m.role })
      newNodes.push(o)
      if (m.location_id) {
        newEdges.push(makeLocatedEdge(nodeId('loc', m.location_id), o.id))
      }
    }

    // Relations between members (labeled command edges).
    for (const rel of data.relations || []) {
      newEdges.push(makeRelationEdge(nodeId('occ', rel.from), nodeId('occ', rel.to), rel.description))
    }

    nodes.value = newNodes
    edges.value = newEdges
    layoutFactionNodes(data)
  }

  function buildGmcWebGraph(data) {
    const newNodes = []
    const newEdges = []

    const gmc = makeOccupantNode({ id: data.gmc.id, name: data.gmc.name, type: 'gmc', location_id: data.location?.id }, {})
    newNodes.push(gmc)

    if (data.location) {
      const loc = makeLocationNode({ _key: data.location.id, name: data.location.name }, { isFocus: true, expanded: true })
      newNodes.push(loc)
      newEdges.push(makeLocatedEdge(loc.id, gmc.id))
    }

    for (const rel of data.relations || []) {
      const other = makeOccupantNode(
        { id: rel.other_id, name: rel.other_name, type: 'gmc', location_id: rel.other_location_id },
        {},
      )
      newNodes.push(other)
      newEdges.push(makeRelationEdge(
        nodeId('occ', rel.from),
        nodeId('occ', rel.to),
        rel.description,
      ))
      if (rel.other_location_id) {
        const otherLocId = nodeId('loc', rel.other_location_id)
        if (!newNodes.find((n) => n.id === otherLocId)) {
          newNodes.push(makeLocationNode({ _key: rel.other_location_id, name: rel.other_location_name }, { expanded: false }))
        }
        newEdges.push(makeLocatedEdge(otherLocId, other.id))
      }
    }

    nodes.value = newNodes
    edges.value = newEdges
    layoutGmcWebNodes()
  }

  // ── Edge factories ──────────────────────────────────

  function makeSuperEdge(source, target) {
    return { id: `super:${source}:${target}`, source, target, type: 'default', data: { kind: 'super' } }
  }
  function makeTransversalEdge(source, target) {
    return { id: `transversal:${source}:${target}`, source, target, type: 'default', data: { kind: 'transversal' }, animated: true, label: 'transversal' }
  }
  function makeLocatedEdge(source, target) {
    return { id: `located:${source}:${target}`, source, target, type: 'default', data: { kind: 'located' } }
  }
  function makeRelationEdge(source, target, label) {
    return { id: `relation:${source}:${target}:${label}`, source, target, type: 'default', label: label || '', data: { kind: 'relation' } }
  }

  // ── Layouts ─────────────────────────────────────────

  function layoutLocationNodes() {
    const focus = nodes.value.find((n) => n.data.isFocus)
    if (!focus) return
    const positions = {}
    positions[focus.id] = { x: 0, y: 0 }

    const parent = edges.value.find((e) => e.target === focus.id && e.data?.kind === 'super')
    const children = edges.value.filter((e) => e.source === focus.id && e.data?.kind === 'super').map((e) => e.target)
    const transversal = edges.value.filter((e) => e.source === focus.id && e.data?.kind === 'transversal').map((e) => e.target)
    const occupants = edges.value.filter((e) => e.source === focus.id && e.data?.kind === 'located').map((e) => e.target)

    if (parent) positions[parent.source] = { x: 0, y: -DY }

    children.forEach((id, i) => {
      positions[id] = { x: (i - (children.length - 1) / 2) * DX, y: DY }
    })

    transversal.forEach((id, i) => {
      positions[id] = { x: DX * 1.5, y: (i - (transversal.length - 1) / 2) * DY }
    })

    occupants.forEach((id, i) => {
      positions[id] = { x: (i - (occupants.length - 1) / 2) * (DX / 1.6), y: DY * 1.6 }
    })

    applyPositions(positions)
  }

  function layoutFactionNodes(data) {
    // Simple grid: locations as columns, members under their location.
    const locNodes = nodes.value.filter((n) => n.type === 'location')
    const positions = {}
    locNodes.forEach((n, i) => {
      positions[n.id] = { x: (i - (locNodes.length - 1) / 2) * DX, y: 0 }
    })
    // Members below their location
    const memberByLoc = {}
    for (const m of data.members || []) {
      if (m.location_id) {
        memberByLoc[m.location_id] = memberByLoc[m.location_id] || []
        memberByLoc[m.location_id].push(nodeId('occ', m.id))
      }
    }
    let row = 1
    for (const locId of Object.keys(memberByLoc)) {
      const members = memberByLoc[locId]
      members.forEach((mid, i) => {
        positions[mid] = { x: positions[nodeId('loc', locId)] ? positions[nodeId('loc', locId)].x + (i - (members.length - 1) / 2) * (DX / 2) : 0, y: DY * row }
      })
    }
    applyPositions(positions)
  }

  function layoutGmcWebNodes() {
    const positions = {}
    const gmc = nodes.value.find((n) => n.type === 'occupant' && n.data.entityId === focusId.value)
    const locs = nodes.value.filter((n) => n.type === 'location')
    const others = nodes.value.filter((n) => n.type === 'occupant' && n.id !== gmc?.id)

    if (gmc) positions[gmc.id] = { x: 0, y: 0 }
    locs.forEach((l, i) => { positions[l.id] = { x: (i - (locs.length - 1) / 2) * DX, y: -DY } })
    others.forEach((o, i) => { positions[o.id] = { x: (i - (others.length - 1) / 2) * DX, y: DY } })

    applyPositions(positions)
  }

  function applyPositions(positions) {
    nodes.value = nodes.value.map((n) => {
      const pos = positions[n.id]
      if (pos) return { ...n, position: { x: pos.x, y: pos.y } }
      return n
    })
  }

  async function loadFactions() {
    try {
      const r = await fetch(`${API_BASE}/graphql`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: 'query { entities { id type name } }' }),
      })
      const data = await r.json()
      factions.value = (data.data?.entities || []).filter((e) => e.type === 'FACTION')
    } catch {
      // non-fatal — faction dropdown just stays empty
    }
  }

  function collapseLocation(locationId) {
    const id = nodeId('loc', locationId)

    // Pin the focus node and its ancestor chain.
    const pinned = new Set()
    const focusNode = nodes.value.find((n) => n.data.isFocus)
    if (focusNode) {
      pinned.add(focusNode.id)
      let current = focusNode.id
      let guard = 0
      while (current && guard++ < 50) {
        const parentEdge = edges.value.find((e) => e.source === current && e.data?.kind === 'super')
        if (!parentEdge) break
        pinned.add(parentEdge.target)
        current = parentEdge.target
      }
    }

    // Collect descendants of the collapsed location via super edges.
    const descendants = new Set()
    const stack = [id]
    while (stack.length) {
      const cur = stack.pop()
      for (const e of edges.value) {
        if (e.target === cur && e.data?.kind === 'super' && !descendants.has(e.source)) {
          descendants.add(e.source)
          stack.push(e.source)
        }
      }
    }

    const removeIds = new Set()
    for (const d of descendants) {
      if (!pinned.has(d)) removeIds.add(d)
    }
    const removedLocEntityIds = new Set(
      nodes.value.filter((n) => removeIds.has(n.id) && n.type === 'location').map((n) => n.data.entityId),
    )
    for (const n of nodes.value) {
      if (n.type === 'occupant' && n.data.locationId && removedLocEntityIds.has(n.data.locationId)) {
        removeIds.add(n.id)
      }
    }

    nodes.value = nodes.value.map((n) => (n.id === id ? { ...n, data: { ...n.data, expanded: false } } : n))
    nodes.value = nodes.value.filter((n) => !removeIds.has(n.id))
    edges.value = edges.value.filter((e) => !removeIds.has(e.source) && !removeIds.has(e.target))

    layoutLocationNodes()
  }

  async function toggleRelations(occId) {
    const occNodeId = nodeId('occ', occId)
    const existing = edges.value.filter(
      (e) => (e.source === occNodeId || e.target === occNodeId) && e.data?.kind === 'relation',
    )
    if (existing.length) {
      edges.value = edges.value.filter((e) => e.source !== occNodeId && e.target !== occNodeId)
      return
    }
    try {
      const r = await fetch(`${API_BASE}/gmcs/${occId}/web`)
      if (!r.ok) return
      const data = await r.json()
      const newNodes = []
      const newEdges = []
      const existingIds = new Set(nodes.value.map((n) => n.id))
      for (const rel of data.relations || []) {
        const otherId = nodeId('occ', rel.other_id)
        if (!existingIds.has(otherId)) {
          newNodes.push(makeOccupantNode({ id: rel.other_id, name: rel.other_name, type: 'gmc', location_id: rel.other_location_id }, {}))
          existingIds.add(otherId)
        }
        newEdges.push(makeRelationEdge(nodeId('occ', rel.from), nodeId('occ', rel.to), rel.description))
        if (rel.other_location_id) {
          const locId = nodeId('loc', rel.other_location_id)
          if (!existingIds.has(locId) && !newNodes.find((n) => n.id === locId)) {
            newNodes.push(makeLocationNode({ _key: rel.other_location_id, name: rel.other_location_name }, { expanded: false }))
            existingIds.add(locId)
          }
          newEdges.push(makeLocatedEdge(locId, otherId))
        }
      }
      nodes.value = [...nodes.value, ...newNodes]
      edges.value = [...edges.value, ...newEdges]
    } catch (e) {
      error.value = e.message
    }
  }

  async function showFaction(occId) {
    const occNode = nodes.value.find((n) => n.id === nodeId('occ', occId))
    const factionList = occNode?.data?.factions || []
    if (factionList.length) {
      await loadFaction(factionList[0].id)
    }
  }

  async function createTransversal(fromId, toId) {
    try {
      const r = await fetch(`${API_BASE}/locations/${fromId}/edges/${toId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'transversal' }),
      })
      if (!r.ok) throw new Error(await r.text())
      edges.value = [...edges.value, makeTransversalEdge(nodeId('loc', fromId), nodeId('loc', toId))]
      layoutLocationNodes()
      return true
    } catch (e) {
      error.value = e.message
      return false
    }
  }

  function setFocus(locationId) {
    // Re-center the graph on a location node.
    const id = nodeId('loc', locationId)
    nodes.value = nodes.value.map((n) => {
      if (n.type === 'location') {
        return { ...n, data: { ...n.data, isFocus: n.id === id } }
      }
      return n
    })
    focusId.value = locationId
    layoutLocationNodes()
  }

  return {
    nodes,
    edges,
    mode,
    focusId,
    title,
    loading,
    error,
    factions,
    loadLocation,
    loadFaction,
    loadGmcWeb,
    expandLocation,
    loadFactions,
    collapseLocation,
    toggleRelations,
    showFaction,
    createTransversal,
    setFocus,
    clear,
  }
}
