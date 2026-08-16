import { ref } from 'vue'
import { MarkerType } from '@vue-flow/core'
import { hierarchy, tree } from 'd3-hierarchy'
import { buildLifePathGraph } from './lifePathGraph.js'
import { nextTransversalType } from './useTransversalLinks.js'

const API_BASE = '/api/v1'

// Module-level singleton state — shared across all canvas instances.
const nodes = ref([])
const edges = ref([])
const mode = ref('location') // 'location' | 'faction' | 'gmc-web' | 'life-path'
const focusId = ref(null)
const title = ref('')
const loading = ref(false)
const error = ref(null)
const layoutOrientation = ref('vertical') // 'vertical' | 'horizontal'

// Persistent knowledge of what the canvas has loaded, keyed by entity id.
// Lets expand/collapse lazily add nodes without refetching already-known ones.
const entityCache = new Map()
const factions = ref([])
let factionsLoaded = false
let currentLifePath = null
let locationTreeData = null
const expandedUniverses = new Set()
let currentUniverse = ''

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
      treeMode: !!opts.treeMode,
    },
  }
}

function makeUniverseNode(uni, opts = {}) {
  const id = nodeId('uni', uni.id)
  return {
    id,
    type: 'universe',
    position: { x: 0, y: 0 },
    data: {
      entityId: uni.id,
      name: uni.name,
      universe: uni.universe,
      isCurrent: !!opts.isCurrent,
      expanded: !!opts.expanded,
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

// ── Orientation helpers ───────────────────────────────

function isHorizontal() {
  return layoutOrientation.value === 'horizontal'
}

function orientationNodeSize() {
  // d3.tree nodeSize uses [sibling-spacing, depth-spacing].
  return isHorizontal() ? [DY, DX] : [DX, DY]
}

function forestSpacing() {
  return isHorizontal() ? DY : DX
}

function depthStep() {
  return isHorizontal() ? DX : DY
}

function depthStepExpanded() {
  return isHorizontal() ? DX * 1.7 : DY * 1.7
}

function mapTreeCoords(sibling, depth) {
  return isHorizontal() ? { x: depth, y: sibling } : { x: sibling, y: depth }
}

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

  async function loadLifePath(lifePath) {
    loading.value = true
    error.value = null
    try {
      mode.value = 'life-path'
      focusId.value = lifePath?.id || null
      title.value = lifePath?.name || 'Life Path'
      currentLifePath = lifePath || null

      if (!lifePath?.entryTableId) {
        nodes.value = []
        edges.value = []
        error.value = 'This life path has no entry table'
        return
      }

      const r = await fetch(`${API_BASE}/graphql`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: `query { rollTables { id name universe lifePath scheme rollSource traitDiceCount die canvasX canvasY entries { label description minValue maxValue weight tier conditions { type target value narrative } effects { timing type action target result targetScope context } } } lifePaths { id name factionIds } }`,
        }),
      })
      const data = await r.json()
      if (!r.ok || data.errors) {
        throw new Error((data.errors && data.errors[0]?.message) || `HTTP ${r.status}`)
      }

      const tables = data.data?.rollTables || []
      const lifePaths = data.data?.lifePaths || []
      await loadFactions()
      const pathMeta = {}
      for (const lp of lifePaths) {
        const factionNames = (lp.factionIds || [])
          .map((id) => factions.value.find((f) => f.id === id)?.name)
          .filter(Boolean)
        pathMeta[lp.id] = { name: lp.name, factionNames }
      }
      const graph = buildLifePathGraph(lifePath, tables, { pathMeta })
      nodes.value = graph.nodes
      edges.value = graph.edges
      if (!tables.length) {
        error.value = 'No roll tables found for this life path'
      } else if (!graph.nodes.length) {
        error.value = 'This life path has no linked roll tables'
      }
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function loadLocationTree(universe) {
    loading.value = true
    error.value = null
    try {
      mode.value = 'location-tree'
      currentUniverse = universe || ''
      focusId.value = null
      title.value = 'Location Tree'

      const r = await fetch(`${API_BASE}/locations/graph`)
      if (!r.ok) throw new Error(await r.text())
      const data = await r.json()
      locationTreeData = data

      expandedUniverses.clear()
      for (const uni of data.tree || []) {
        if (uni.node_type === 'universe' && uni.universe === currentUniverse) expandedUniverses.add(uni.id)
      }

      buildLocationTreeGraph()
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  function toggleUniverseExpand(universeId) {
    if (!locationTreeData) return
    if (expandedUniverses.has(universeId)) expandedUniverses.delete(universeId)
    else expandedUniverses.add(universeId)
    buildLocationTreeGraph()
  }

  function buildLocationTreeGraph() {
    if (!locationTreeData) return
    const newNodes = []
    const newEdges = []

    for (const node of locationTreeData.tree || []) {
      if (node.node_type === 'universe') {
        const expanded = expandedUniverses.has(node.id)
        newNodes.push(makeUniverseNode(node, { isCurrent: node.universe === currentUniverse, expanded }))
        if (expanded) {
          for (const loc of node.children || []) {
            addLocationSubtree(loc, nodeId('uni', node.id), newNodes, newEdges)
          }
        }
      } else {
        // Orphan location (no matching universe) rendered as a top-level node.
        addLocationSubtree(node, null, newNodes, newEdges)
      }
    }

    const locIds = new Set(newNodes.filter((n) => n.type === 'location').map((n) => n.data.entityId))
    for (const t of locationTreeData.transversal || []) {
      if (locIds.has(t.from) && locIds.has(t.to)) {
        newEdges.push(makeTransversalEdge(nodeId('loc', t.from), nodeId('loc', t.to), t.transversal_type))
      }
    }

    nodes.value = newNodes
    edges.value = newEdges
    layoutLocationTreeNodes()
  }

  function addLocationSubtree(loc, parentId, newNodes, newEdges) {
    const id = nodeId('loc', loc.id)
    newNodes.push(makeLocationNode({ _key: loc.id, name: loc.name, current_universe: loc.universe }, { expanded: true, treeMode: true }))
    if (parentId) newEdges.push(makeSuperEdge(id, parentId))
    for (const child of loc.children || []) {
      addLocationSubtree(child, id, newNodes, newEdges)
    }
  }

  function layoutLocationTreeNodes() {
    layoutLocationForest({ includeUniverse: true })
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

  function toggleLayoutOrientation() {
    layoutOrientation.value = isHorizontal() ? 'vertical' : 'horizontal'
    if (mode.value === 'location-tree') layoutLocationTreeNodes()
    else if (mode.value === 'location') layoutLocationNodes()
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
      newEdges.push(makeTransversalEdge(focus.id, p.id, peer.transversal_type))
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
        newEdges.push(makeTransversalEdge(expandedLocId, p.id, peer.transversal_type))
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
    for (const [id, loc] of locById) {
      newNodes.push(makeLocationNode({ _key: id, name: loc.name, current_universe: loc.universe }, { isScaffolding: loc.scaffolding, expanded: true }))
    }

    // Super edges connecting the pruned location tree (child → parent).
    for (const e of data.location_edges || []) {
      if (locById.has(e.child) && locById.has(e.parent)) {
        newEdges.push(makeSuperEdge(nodeId('loc', e.child), nodeId('loc', e.parent)))
      }
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
    return { id: `super:${source}:${target}`, source, target, type: 'default', data: { kind: 'super' }, sourceHandle: 'top', targetHandle: 'bottom' }
  }
  function makeTransversalEdge(source, target, transversalType) {
    const t = transversalType === 'consciousness' ? 'consciousness' : 'inapposite'
    return { id: `transversal:${source}:${target}`, source, target, type: 'default', data: { kind: 'transversal', transversalType: t }, animated: true, label: t, style: { stroke: t === 'consciousness' ? '#f59e0b' : '#8b5cf6' }, sourceHandle: 'right', targetHandle: 'left', markerStart: MarkerType.ArrowClosed, markerEnd: MarkerType.ArrowClosed }
  }
  function makeLocatedEdge(source, target) {
    return { id: `located:${source}:${target}`, source, target, type: 'default', data: { kind: 'located' }, sourceHandle: 'bottom-source', targetHandle: 'target-top' }
  }
  function makeRelationEdge(source, target, label) {
    return { id: `relation:${source}:${target}:${label}`, source, target, type: 'gradient', label: label || '', data: { kind: 'relation' } }
  }

  // ── Layouts ─────────────────────────────────────────

  function layoutLocationNodes() {
    const focus = nodes.value.find((n) => n.data.isFocus)
    if (!focus) return
    layoutLocationForest({ centerId: focus.id })
  }

  function buildLocationHierarchy(includeUniverse = false) {
    const parentOf = {}
    const childrenOf = {}
    const hierarchyIds = new Set(
      nodes.value
        .filter((n) => n.type === 'location' || (includeUniverse && n.type === 'universe'))
        .map((n) => n.id),
    )
    for (const e of edges.value) {
      if (e.data?.kind === 'super' && hierarchyIds.has(e.source) && hierarchyIds.has(e.target)) {
        parentOf[e.source] = e.target
        childrenOf[e.target] = childrenOf[e.target] || []
        childrenOf[e.target].push(e.source)
      }
    }
    const roots = [...hierarchyIds].filter((id) => !parentOf[id])
    return { parentOf, childrenOf, hierarchyIds, roots }
  }

  function layoutLocationForest({ includeUniverse = false, centerId = null } = {}) {
    const { parentOf, childrenOf, hierarchyIds, roots } = buildLocationHierarchy(includeUniverse)

    const buildData = (id) => ({
      id,
      children: (childrenOf[id] || []).filter((cid) => hierarchyIds.has(cid)).map(buildData),
    })

    // d3.tree assigns the sibling coordinate; depth is assigned by the
    // occupant-aware walk below so sub-locations stay clear of occupants.
    const positions = {}
    let forestOffset = 0
    const layout = tree().nodeSize(orientationNodeSize())
    for (const rootId of roots) {
      const root = hierarchy(buildData(rootId))
      layout(root)
      let minSibling = Infinity
      let maxSibling = -Infinity
      root.each((d) => {
        minSibling = Math.min(minSibling, d.x)
        maxSibling = Math.max(maxSibling, d.x)
      })
      const center = (minSibling + maxSibling) / 2
      root.each((d) => {
        const c = mapTreeCoords(d.x - center + forestOffset, d.y)
        positions[d.data.id] = { x: c.x, y: c.y }
      })
      forestOffset += (maxSibling - minSibling) + forestSpacing()
    }

    // Center the focus on the cross axis.
    if (centerId && positions[centerId]) {
      const c = positions[centerId]
      if (isHorizontal()) {
        for (const id of Object.keys(positions)) positions[id].y -= c.y
      } else {
        for (const id of Object.keys(positions)) positions[id].x -= c.x
      }
    }

    // Occupants per location (located edge: source=location, target=occupant).
    const occupantsOf = {}
    for (const e of edges.value) {
      if (e.data?.kind === 'located' && hierarchyIds.has(e.source)) {
        occupantsOf[e.source] = occupantsOf[e.source] || []
        occupantsOf[e.source].push(e.target)
      }
    }

    // Walk the hierarchy assigning depth coordinates; occupants sit below
    // their location, and sub-locations drop further when occupants exist.
    const seen = new Set()
    function walk(nodeId, depth) {
      if (seen.has(nodeId)) return
      seen.add(nodeId)
      const pos = positions[nodeId]
      if (!pos) return
      if (isHorizontal()) pos.x = depth
      else pos.y = depth

      const occupants = occupantsOf[nodeId] || []
      const children = (childrenOf[nodeId] || []).filter((cid) => hierarchyIds.has(cid))

      occupants.forEach((oid, i) => {
        positions[oid] = {
          x: pos.x + DX * 0.55 + (i - (occupants.length - 1) / 2) * (DX / 2),
          y: pos.y + DY * 0.7,
        }
      })

      const childDepth = depth + (occupants.length ? depthStepExpanded() : depthStep())
      children.forEach((cid) => walk(cid, childDepth))
    }

    if (centerId) {
      const chain = []
      let cur = centerId
      while (parentOf[cur]) {
        chain.push(parentOf[cur])
        cur = parentOf[cur]
      }
      const mainRoot = chain.length ? chain[chain.length - 1] : centerId
      walk(mainRoot, 0)

      const f = positions[centerId]
      const fDepth = f ? (isHorizontal() ? f.x : f.y) : 0
      for (const id of Object.keys(positions)) {
        if (isHorizontal()) positions[id].x -= fDepth
        else positions[id].y -= fDepth
      }

      for (const rootId of roots) {
        if (!seen.has(rootId)) walk(rootId, 0)
      }
    } else {
      for (const rootId of roots) walk(rootId, 0)
    }

    applyPositions(positions)
  }

  function layoutFactionNodes(data) {
    // Build a forest of location trees from super edges, then lay each tree
    // out top-to-bottom with d3.tree.
    const parentOf = {}
    const childrenOf = {}
    for (const e of edges.value) {
      if (e.data?.kind === 'super') {
        parentOf[e.source] = e.target
        childrenOf[e.target] = childrenOf[e.target] || []
        childrenOf[e.target].push(e.source)
      }
    }

    const locNodeIds = new Set(nodes.value.filter((n) => n.type === 'location').map((n) => n.id))
    const roots = [...locNodeIds].filter((id) => !parentOf[id])

    const buildData = (id) => ({
      id,
      children: (childrenOf[id] || []).map(buildData),
    })

    const positions = {}
    let offsetX = 0
    const layout = tree().nodeSize([DX, DY])
    for (const rootId of roots) {
      const root = hierarchy(buildData(rootId))
      layout(root)
      let minX = Infinity
      let maxX = -Infinity
      root.each((d) => {
        minX = Math.min(minX, d.x)
        maxX = Math.max(maxX, d.x)
      })
      const center = (minX + maxX) / 2
      root.each((d) => {
        positions[d.data.id] = { x: d.x - center + offsetX, y: d.y }
      })
      offsetX += (maxX - minX) + DX
    }

    // Members directly below their location.
    const memberByLoc = {}
    for (const m of data.members || []) {
      if (m.location_id) {
        memberByLoc[m.location_id] = memberByLoc[m.location_id] || []
        memberByLoc[m.location_id].push(nodeId('occ', m.id))
      }
    }
    for (const locId of Object.keys(memberByLoc)) {
      const locNodeId = nodeId('loc', locId)
      const base = positions[locNodeId]
      if (!base) continue
      const members = memberByLoc[locId]
      members.forEach((mid, i) => {
        positions[mid] = {
          x: base.x + (i - (members.length - 1) / 2) * (DX / 2),
          y: base.y + DY * 0.8,
        }
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
    routeEdges()
  }

  function routeEdges() {
    // For relation edges, pick the handle pair on the sides facing each other
    // (closest sides). Reciprocal edges between the same pair get distinct
    // vertical lanes (upper/lower) so they no longer overlap.
    const pos = {}
    for (const n of nodes.value) pos[n.id] = n.position

    // Deterministic lane assignment per unordered node pair, independent of
    // insertion order (edges arrive lazily via expand / toggleRelations).
    const groups = new Map()
    const laneOf = new Map()
    for (const e of edges.value) {
      if (e.data?.kind !== 'relation') continue
      const key = [e.source, e.target].sort().join('|')
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key).push(e)
    }
    for (const group of groups.values()) {
      group.sort((a, b) => (a.source === b.source ? a.target.localeCompare(b.target) : a.source.localeCompare(b.source)))
      group.forEach((e, i) => { laneOf.set(e.id, i) })
    }

    edges.value = edges.value.map((e) => {
      if (e.data?.kind === 'super') {
        if (isHorizontal()) {
          const targetNode = nodes.value.find((n) => n.id === e.target)
          const targetHandle = targetNode?.type === 'universe' ? 'right' : 'right-target'
          return { ...e, sourceHandle: 'left-source', targetHandle }
        }
        return { ...e, sourceHandle: 'top', targetHandle: 'bottom' }
      }
      if (e.data?.kind !== 'relation') return e
      const s = pos[e.source]
      const t = pos[e.target]
      if (!s || !t) return e
      const dx = t.x - s.x
      const dy = t.y - s.y
      const suffix = (laneOf.get(e.id) || 0) % 2 === 0 ? 'a' : 'b'
      let sourceHandle
      let targetHandle
      if (Math.abs(dx) >= Math.abs(dy)) {
        // Horizontal → left/right lane handles (upper/lower).
        sourceHandle = `source-${dx >= 0 ? 'right' : 'left'}-${suffix}`
        targetHandle = `target-${dx >= 0 ? 'left' : 'right'}-${suffix}`
      } else {
        // Vertical → single top/bottom handles (lanes deferred).
        sourceHandle = dy >= 0 ? 'source-bottom' : 'source-top'
        targetHandle = dy >= 0 ? 'target-top' : 'target-bottom'
      }
      return { ...e, sourceHandle, targetHandle }
    })
  }

  async function loadFactions() {
    if (factionsLoaded) return
    try {
      const r = await fetch(`${API_BASE}/graphql`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: 'query { entities { id type name } }' }),
      })
      const data = await r.json()
      factions.value = (data.data?.entities || []).filter((e) => e.type === 'FACTION')
      factionsLoaded = true
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
      // Remove only relation edges touching this occupant — keep the
      // located (occupant → location) edge and any other non-relation edges.
      edges.value = edges.value.filter(
        (e) => !(e.data?.kind === 'relation' && (e.source === occNodeId || e.target === occNodeId)),
      )
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
      routeEdges()
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

  async function createRelation(fromId, toId) {
    try {
      const r = await fetch(`${API_BASE}/graphql`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: `mutation($input: CreateRelationshipInput!){ createRelationship(input:$input){ id } }`,
          variables: { input: { fromEntityId: fromId, toEntityId: toId, type: 'associate', description: '' } },
        }),
      })
      const data = await r.json()
      if (!r.ok || data.errors) throw new Error((data.errors && data.errors[0]?.message) || `HTTP ${r.status}`)
      edges.value = [...edges.value, makeRelationEdge(nodeId('occ', fromId), nodeId('occ', toId), '')]
      routeEdges()
      return true
    } catch (e) {
      error.value = e.message
      return false
    }
  }

  async function linkRollTable(sourceTableId, rowIndex, targetTableId) {
    try {
      // Fetch the full source table so we can modify one entry without guessing.
      const fr = await fetch(`${API_BASE}/graphql`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: `query($id:ID!){ rollTable(id:$id){ id name universe lifePath scheme rollSource traitDiceCount die check { traitIds difficulty freeChoice } entries { label description minValue maxValue weight tier conditions { type target value narrative } effects { timing type action target result targetScope context } } } }`,
          variables: { id: sourceTableId },
        }),
      })
      const fd = await fr.json()
      if (!fr.ok || fd.errors) throw new Error((fd.errors && fd.errors[0]?.message) || `HTTP ${fr.status}`)

      const table = fd.data?.rollTable
      const entry = table?.entries?.[rowIndex]
      if (!table || !entry) return false

      const nextEffect = { timing: 'IMMEDIATE', type: 'life_path', action: 'next_step', target: targetTableId, result: null, targetScope: null, context: {} }
      const entries = table.entries.map((e, i) => (
        i === rowIndex ? { ...e, effects: [...(e.effects || []), nextEffect] } : e
      ))

      const sr = await fetch(`${API_BASE}/graphql`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: `mutation($input: RollTableInput!){ saveRollTable(input:$input){ id } }`,
          variables: {
            input: {
              id: table.id,
              name: table.name,
              universe: table.universe,
              lifePath: table.lifePath,
              scheme: table.scheme,
              rollSource: table.rollSource,
              traitDiceCount: table.traitDiceCount,
              die: table.die,
              check: table.check,
              entries,
            },
          },
        }),
      })
      const sd = await sr.json()
      if (!sr.ok || sd.errors) throw new Error((sd.errors && sd.errors[0]?.message) || `HTTP ${sr.status}`)

      // Reload so the new link (and any out-of-path target) renders.
      if (currentLifePath) await loadLifePath(currentLifePath)
      return true
    } catch (e) {
      error.value = e.message
      return false
    }
  }

  async function toggleTransversalEdge(edge) {
    if (edge?.data?.kind !== 'transversal') return
    const fromId = edge.source.replace('loc:', '')
    const toId = edge.target.replace('loc:', '')
    const next = nextTransversalType(edge.data.transversalType)
    try {
      const r = await fetch(`${API_BASE}/locations/${fromId}/edges/${toId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'transversal', transversal_type: next }),
      })
      if (!r.ok) throw new Error(await r.text())
      edges.value = edges.value.map((e) => e.id === edge.id ? makeTransversalEdge(e.source, e.target, next) : e)
    } catch (e) {
      error.value = e.message
    }
  }

  async function persistTablePosition(tableId, x, y) {
    try {
      await fetch(`${API_BASE}/graphql`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: `mutation($id:ID!,$x:Float,$y:Float){ setRollTablePosition(id:$id,x:$x,y:$y){ id } }`,
          variables: { id: tableId, x, y },
        }),
      })
    } catch {
      // non-fatal — layout persistence shouldn't break the canvas
    }
  }

  async function clearLifePathPositions(lifePathId) {
    try {
      await fetch(`${API_BASE}/graphql`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: `mutation($lp:ID!){ clearRollTablePositions(lifePathId:$lp) }`,
          variables: { lp: lifePathId },
        }),
      })
    } catch {
      // non-fatal
    }
  }

  function setFocus(locationId) {
    // Highlight the node without repositioning the graph.
    const id = nodeId('loc', locationId)
    nodes.value = nodes.value.map((n) => {
      if (n.type === 'location') {
        return { ...n, data: { ...n.data, isFocus: n.id === id } }
      }
      return n
    })
    focusId.value = locationId
  }

  function updateNodePosition(id, position) {
    const old = nodes.value.find((n) => n.id === id)
    const dx = position.x - (old?.position?.x ?? position.x)
    const dy = position.y - (old?.position?.y ?? position.y)
    const isTable = old?.type === 'rolltable'
    const parentId = old?.data?.entityId
    nodes.value = nodes.value.map((n) => {
      if (n.id === id) return { ...n, position: { ...position } }
      // Bundlers stay glued to the table whose rows they fan in from.
      if (isTable && n.type === 'bundler' && n.data?.parentId === parentId) {
        return { ...n, position: { x: n.position.x + dx, y: n.position.y + dy } }
      }
      return n
    })
    if (isTable && parentId) persistTablePosition(parentId, position.x, position.y)
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
    layoutOrientation,
    toggleLayoutOrientation,
    loadLocation,
    loadFaction,
    loadGmcWeb,
    loadLifePath,
    loadLocationTree,
    toggleUniverseExpand,
    expandLocation,
    loadFactions,
    collapseLocation,
    toggleRelations,
    showFaction,
    createTransversal,
    createRelation,
    linkRollTable,
    toggleTransversalEdge,
    setFocus,
    updateNodePosition,
    persistTablePosition,
    clearLifePathPositions,
    clear,
  }
}
