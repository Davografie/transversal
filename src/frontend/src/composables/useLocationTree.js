import { ref, computed } from 'vue'

// ── Module-level singleton state ─────────────────────
const locationTree = ref([])
const expandedNodes = ref({})

// ── Constants ────────────────────────────────────────
const TYPE_PRIORITY = { CHARACTER: 0, GMC: 1, ASSET: 2 }
const OCCUPANT_TYPES = new Set(['CHARACTER', 'GMC', 'ASSET'])

export function useLocationTree({ filteredEntities, activeFilters, currentUniverse }) {
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
    function markAncestors(nodes, targetSet) {
      for (const n of nodes) {
        let hasOccupiedDescendant = false
        if (n.children) hasOccupiedDescendant = markAncestors(n.children, targetSet)
        if (targetSet.has(n.id) || hasOccupiedDescendant) {
          set.add(n.id)
          return true
        }
      }
      return false
    }
    markAncestors(locationTree.value, set)
    return set
  })

  // ── Flatten ────────────────────────────────────────
  function flattenTree(nodes, occupants, depth = 0) {
    const result = []
    const filterMode = hasOccupantFilter.value
    const populated = populatedLocations.value
    const curUniverse = currentUniverse?.value || ''
    for (const node of nodes) {
      const kind = node.kind || (node.node_type === 'universe' ? 'universe' : 'location')
      if (activeUniverseFilters.value.size > 0) {
        if (kind === 'universe' && node.universe && !activeUniverseFilters.value.has(node.universe)) continue
        if (kind === 'location' && depth === 0 && node.universe && !activeUniverseFilters.value.has(node.universe)) continue
      }
      // In filter mode only render nodes on the populated path, which hides
      // sibling locations and unrelated universes.
      const onPath = filterMode && populated.has(node.id)
      if (filterMode && !onPath) continue
      const hasChildren = (node.children && node.children.length > 0) ||
        (occupants[node.id] && occupants[node.id].length > 0)
      let expanded
      if (expandedNodes.value[node.id] !== undefined) {
        expanded = expandedNodes.value[node.id]
      } else if (filterMode) {
        expanded = false
      } else {
        expanded = depth === 0 && node.universe === curUniverse
      }
      result.push({
        id: node.id, name: node.name, universe: node.universe,
        depth, hasChildren, kind, expanded,
      })
      // In filter mode also reveal the occupant on a collapsed leaf.
      if (expanded || (filterMode && occupants[node.id] && occupants[node.id].length)) {
        for (const e of occupants[node.id] || []) {
          result.push({
            id: e.id, name: e.name, universe: e.currentUniverse || '',
            depth: depth + 1, hasChildren: false, kind: 'occupant',
            entityType: e.type, entity: e,
          })
        }
      }
      if (expanded && kind === 'universe' && node.universe) {
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
      if (node.children && node.children.length) {
        if (expanded) {
          result.push(...flattenTree(node.children, occupants, depth + 1))
        } else if (filterMode && onPath) {
          // Collapsed but on the focus path: render only the on-path child.
          const next = node.children.filter((c) => populated.has(c.id))
          if (next.length) result.push(...flattenTree(next, occupants, depth + 1))
        }
      }
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

  return {
    locationTree,
    expandedNodes,
    fetchLocationTree,
    toggleTreeNode,
    flatTree,
    occupantsByLocation,
    findAncestorIds,
  }
}
