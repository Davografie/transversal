import { ref, computed } from 'vue'

// ── Module-level singleton state ─────────────────────
const locationTree = ref([])
const expandedNodes = ref({})
// The node the tree focuses on (the GM's current location in free-roam). While
// set, the tree renders the ancestor chain and collapses each level's other
// children into a single "… N more" stub row — see flattenTree.
const focusId = ref('')

// ── Constants ────────────────────────────────────────
const TYPE_PRIORITY = { CHARACTER: 0, GMC: 1, ASSET: 2 }
const OCCUPANT_TYPES = new Set(['CHARACTER', 'GMC', 'ASSET'])

export function useLocationTree({ filteredEntities, activeFilters, currentUniverse }) {
  // The focused node: its ancestor chain stays expanded, its siblings stub.
  function setFocus(id) {
    focusId.value = id || ''
  }
  // ── Fetch ──────────────────────────────────────────
  async function fetchLocationTree() {
    try {
      const r = await fetch('/api/v1/locations/tree')
      locationTree.value = await r.json()
    } catch {
      locationTree.value = []
    }
  }

  function toggleTreeNode(id) {
    expandedNodes.value = { ...expandedNodes.value, [id]: !expandedNodes.value[id] }
  }

  // ── Occupant grouping ──────────────────────────────
  function _sortOccupants(arr) {
    arr.sort((a, b) => (TYPE_PRIORITY[a.type] ?? 9) - (TYPE_PRIORITY[b.type] ?? 9))
  }

  const occupantsByLocation = computed(() => {
    const map = {}
    for (const e of (filteredEntities?.value ?? [])) {
      if (OCCUPANT_TYPES.has(e.type) && e.currentLocation) {
        if (!map[e.currentLocation]) map[e.currentLocation] = []
        map[e.currentLocation].push(e)
      }
    }
    for (const key of Object.keys(map)) _sortOccupants(map[key])
    return map
  })

  const unplacedByUniverse = computed(() => {
    const map = {}
    for (const e of (filteredEntities?.value ?? [])) {
      if (OCCUPANT_TYPES.has(e.type) && !e.currentLocation && e.currentUniverse) {
        if (!map[e.currentUniverse]) map[e.currentUniverse] = []
        map[e.currentUniverse].push(e)
      }
    }
    for (const key of Object.keys(map)) _sortOccupants(map[key])
    return map
  })

  // ── Filter-aware location helpers ──────────────────
  const hasOccupantFilter = computed(() =>
    (activeFilters?.value ?? []).some(f => f.type === 'entityType' || f.type === 'name')
  )

  const activeUniverseFilters = computed(() => {
    const keys = new Set()
    for (const f of (activeFilters?.value ?? [])) {
      if (f.type === 'universe') keys.add(f.value)
    }
    return keys
  })

  const populatedLocations = computed(() => {
    const occ = occupantsByLocation.value
    const set = new Set(Object.keys(occ))
    // A place that matched the filter by name must draw itself even when nobody
    // is standing in it. Occupants are the only other seed and a LOCATION entity
    // is not an occupant, so a place holding nobody directly (only nested towns)
    // had no populated node on its path at all — filter mode then skipped every
    // row and the tree came back empty.
    if (hasOccupantFilter.value) {
      for (const e of (filteredEntities?.value ?? [])) {
        if (e.type === 'LOCATION') set.add(e.id)
      }
    }
    // Mark every node that holds (or contains, at any depth) a matching
    // occupant. Must visit ALL siblings — an early `return true` here leaves
    // later branches unmarked, and `flattenTree` only descends into marked
    // nodes, so their occupants silently vanish in filter mode.
    function markAncestors(nodes, targetSet) {
      let anyMarked = false
      for (const n of nodes) {
        let hasOccupiedDescendant = false
        if (n.children) hasOccupiedDescendant = markAncestors(n.children, targetSet)
        if (targetSet.has(n.id) || hasOccupiedDescendant) {
          set.add(n.id)
          anyMarked = true
        }
      }
      return anyMarked
    }
    markAncestors(locationTree.value, set)
    return set
  })

  // ── Focus: the breadcrumb chain (root → focused node) ──
  // While a focus is set, flattenTree renders this chain and stubs the
  // off-chain siblings at each level instead of expanding the whole level.
  function _findTrail(nodes, targetId, trail) {
    for (const n of nodes) {
      trail.push(n)
      if (n.id === targetId) return true
      if (n.children && _findTrail(n.children, targetId, trail)) return true
      trail.pop()
    }
    return false
  }

  const focusPath = computed(() => {
    if (!focusId.value || !locationTree.value.length) return []
    const trail = []
    if (!_findTrail(locationTree.value, focusId.value, trail)) return []
    return trail.map((n) => ({
      id: n.id, name: n.name,
      kind: n.kind || (n.node_type === 'universe' ? 'universe' : 'location'),
    }))
  })
  const focusPathIds = computed(() => new Set(focusPath.value.map((n) => n.id)))

  function collapseAll() {
    expandedNodes.value = {}
  }

  // ── Flatten ────────────────────────────────────────
  // Synthetic key for the virtual root, so the top level can be stubbed like
  // any other level ("… N more universes").
  const ROOT_KEY = '__root__'

  // Inline "add" rows hang off the end of their collection. They are only
  // offered while browsing the whole tree: with filters or focus active the
  // list shows a curated subset, so "the end of the collection" is not a
  // stable place to put them.
  const showAddRows = computed(() =>
    !hasOccupantFilter.value && !activeUniverseFilters.value.size && focusPathIds.value.size === 0
  )

  function flattenTree(nodes, occupants, depth = 0) {
    const result = []
    const filterMode = hasOccupantFilter.value
    const populated = populatedLocations.value
    const curUniverse = currentUniverse?.value || ''
    const focusSet = focusPathIds.value
    // A filter and a focus are two answers to "what is on screen", and the
    // focus's answer is the wrong one. Focus mode stubs a level's off-chain
    // children behind "… N more", so a filter match sitting off the focus chain
    // was hidden behind that stub; and the ROOT stub's count is computed from
    // the focus chain, which is how "… 17 more universes" came to sit above an
    // empty list and expand to "No entities found". While any filter is active
    // the filter decides, so focus stubbing is off — filter mode already drills
    // the populated paths on its own.
    const filtering = filterMode || activeUniverseFilters.value.size > 0
    const focusMode = focusSet.size > 0 && !filtering
    // At the root level, focus mode keeps only the focused universe on screen
    // and stubs the others, until the level is expanded (the stub click).
    const rootStubbed = depth === 0 && focusMode && expandedNodes.value[ROOT_KEY] !== true
    if (rootStubbed) {
      const onChain = nodes.filter((n) => focusSet.has(n.id))
      if (onChain.length) nodes = onChain
    }
    for (const node of nodes) {
      const kind = node.kind || (node.node_type === 'universe' ? 'universe' : 'location')
      // Universe chips narrow a universe-only filter to its universes. Once an
      // occupant chip (name/type) is in play the chips are a union (OR), so
      // pruning by universe would hide exactly what the other chips bring in;
      // the populated-path prune below already shows the right paths.
      if (activeUniverseFilters.value.size > 0 && !hasOccupantFilter.value) {
        if (kind === 'universe' && node.universe && !activeUniverseFilters.value.has(node.universe)) continue
        if (kind === 'location' && depth === 0 && node.universe && !activeUniverseFilters.value.has(node.universe)) continue
      }
      // In filter mode only render nodes on the populated path, which hides
      // sibling locations and unrelated universes.
      const onPath = filterMode && populated.has(node.id)
      if (filterMode && !onPath) continue
      const onFocus = focusMode && focusSet.has(node.id)

      // Focus mode: a level of the chain shows its on-chain child(ren) and
      // collapses every other child into one "… N more" stub, until that
      // level is explicitly expanded (which renders all of its children).
      const kids = node.children || []
      const showAllKids = !focusMode || !onFocus || expandedNodes.value[node.id] === true
      const visibleKids = showAllKids ? kids : kids.filter((c) => focusSet.has(c.id))

      let expanded
      if (expandedNodes.value[node.id] !== undefined) {
        expanded = expandedNodes.value[node.id]
      } else if (filterMode) {
        expanded = false
      } else if (focusMode) {
        expanded = onFocus
      } else {
        expanded = depth === 0 && node.universe === curUniverse
      }
      const hasChildren = kids.length > 0 ||
        (occupants[node.id] && occupants[node.id].length > 0)
      result.push({
        id: node.id, name: node.name, universe: node.universe,
        depth, hasChildren, kind,
        // The glyph reflects what is on screen: a chain level that shows its
        // child renders as expanded even though it is not fully expanded.
        expanded: expanded || (focusMode && onFocus && visibleKids.length > 0),
      })
      // In filter mode also reveal the occupant on a collapsed leaf. In focus
      // mode only the focused place itself (and levels the GM expanded by hand)
      // lists occupants — otherwise every ancestor's roster would bloat the
      // chain.
      const revealOccupants = !focusMode || expandedNodes.value[node.id] === true || node.id === focusId.value
      if ((expanded && revealOccupants) || (filterMode && occupants[node.id] && occupants[node.id].length)) {
        for (const e of occupants[node.id] || []) {
          result.push({
            id: e.id, name: e.name, universe: e.currentUniverse || '',
            depth: depth + 1, hasChildren: false, kind: 'occupant',
            entityType: e.type, entity: e,
          })
        }
        // Occupants live in locations, so the row trails each location's roster.
        if (kind === 'location' && expanded && showAddRows.value) {
          result.push({
            id: 'add:occupant:' + node.id, kind: 'add', addType: 'occupant',
            parentId: node.id, universe: node.universe || '', depth: depth + 1,
            hasChildren: false, name: 'add occupant',
          })
        }
      }
      if (expanded && kind === 'universe' && node.universe && revealOccupants) {
        const unplaced = unplacedByUniverse.value[node.universe]
        if (unplaced) {
          for (const e of unplaced) {
            result.push({
              id: e.id, name: e.name, universe: e.currentUniverse || '',
              depth: depth + 1, hasChildren: false, kind: 'occupant',
              entityType: e.type, entity: e,
            })
          }
        }
      }
      if (kids.length) {
        if (expanded) {
          result.push(...flattenTree(visibleKids, occupants, depth + 1))
        } else if (filterMode && onPath) {
          // Collapsed but on the focus path: render only the on-path child.
          const next = kids.filter((c) => populated.has(c.id))
          if (next.length) result.push(...flattenTree(next, occupants, depth + 1))
        }
        if (focusMode && onFocus && expanded && !showAllKids) {
          const hidden = kids.length - visibleKids.length
          if (hidden > 0) {
            result.push({
              id: 'more:' + node.id, kind: 'more', parentId: node.id, count: hidden,
              name: `… ${hidden} more`, depth: depth + 1, hasChildren: false,
            })
          }
        }
      }
      // Locations are placed in a universe, so the row trails that universe's
      // children — including when it has none yet.
      if (kind === 'universe' && expanded && showAddRows.value && node.universe) {
        result.push({
          id: 'add:location:' + node.id, kind: 'add', addType: 'location',
          parentId: node.id, universe: node.universe, depth: depth + 1,
          hasChildren: false, name: 'add location',
        })
      }
    }
    // Root-level stub: the universes focus mode is hiding.
    if (depth === 0 && focusMode && expandedNodes.value[ROOT_KEY] !== true) {
      const hidden = locationTree.value.length - nodes.length
      if (hidden > 0) {
        result.push({
          id: 'more:' + ROOT_KEY, kind: 'more', parentId: ROOT_KEY, count: hidden,
          name: `… ${hidden} more universes`, depth: 0, hasChildren: false,
        })
      }
    }
    // Universes are the top level, so their "add" row closes the whole tree.
    if (depth === 0 && showAddRows.value) {
      result.push({
        id: 'add:universe', kind: 'add', addType: 'universe',
        parentId: '', universe: '', depth: 0, hasChildren: false, name: 'add universe',
      })
    }
    return result
  }

  const flatTree = computed(() => {
    return flattenTree(locationTree.value, occupantsByLocation.value, 0)
  })

  // ── Ancestor path ──────────────────────────────────
  function findAncestorIds(nodes, targetId, path) {
    for (const n of nodes) {
      path.push(n.id)
      if (n.id === targetId) return true
      if (n.children && findAncestorIds(n.children, targetId, path)) return true
      path.pop()
    }
    return false
  }

  // ── Scene scope ─────────────────────────────────────
  // The scene summary should show only entities in the current location, its
  // ancestors, and its descendants — not every entity in the multiverse.
  function _findNodeWithAncestors(nodes, targetId, ancestors) {
    for (const n of nodes) {
      if (n.id === targetId) return n
      if (n.children && n.children.length) {
        ancestors.push(n)
        const found = _findNodeWithAncestors(n.children, targetId, ancestors)
        if (found) return found
        ancestors.pop()
      }
    }
    return null
  }

  function _collectDescendants(node, set) {
    if (!node) return
    for (const c of node.children || []) {
      set.add(c.id)
      _collectDescendants(c, set)
    }
  }

  function sceneLocationIds(targetId) {
    const set = new Set()
    if (!targetId) return set
    // Always include the current location itself, even before the tree loads.
    set.add(targetId)
    if (!locationTree.value.length) return set
    const ancestors = []
    const target = _findNodeWithAncestors(locationTree.value, targetId, ancestors)
    if (!target) return set
    for (const a of ancestors) set.add(a.id)
    _collectDescendants(target, set)
    return set
  }

  return {
    locationTree,
    focusPath,
    focusId,
    setFocus,
    collapseAll,
    expandedNodes,
    fetchLocationTree,
    toggleTreeNode,
    flatTree,
    occupantsByLocation,
    findAncestorIds,
    sceneLocationIds,
  }
}
