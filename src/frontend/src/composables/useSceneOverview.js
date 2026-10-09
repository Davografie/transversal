import { computed, unref } from 'vue'

// ── The scene, as the play surface reads it ──────────────────
// "The scene" is the place the GM is standing in and everyone in it: the roster
// *here*, plus its ancestors and its sub-locations as drawers, because the
// roster is the thing being run and the wider picture is a click away.
//
// It lives in a composable rather than in one host because it now has **two**:
// the GM panel's Play tab and the roaming GM's sheet both draw this surface, and
// two copies of the parent/zone grouping would drift the first time one of them
// was touched. Both hosts pass their own data in, so the composable owns no
// fetching — the panel reads the tree the GM filters, the sheet reads the shared
// singleton — and only owns the shape.
//
// The current location is read from a getter or a ref (the hosts hold it
// differently: a prop in one, a prop in the other), so the unref is deliberate
// rather than defensive.
export function useSceneOverview({ entities, locationTree, currentLocationId }) {
  // Every occupant type, assets included, and deliberately **unfiltered** — the
  // panel's focus chips belong to Prep. The Play screen shows the scene as it
  // is; the GM's own acting-entity chip must not narrow it.
  const SCENE_TYPE_PRIORITY = { CHARACTER: 0, GMC: 1, ASSET: 2 }

  const occupants = computed(() =>
    (unref(entities) || []).filter((e) => e.type in SCENE_TYPE_PRIORITY)
  )

  function findTreeNode(nodes, id) {
    for (const n of (nodes || [])) {
      if (n.id === id) return n
      const hit = findTreeNode(n.children || [], id)
      if (hit) return hit
    }
    return null
  }

  function entitiesAt(locationId) {
    return occupants.value.filter((e) => e.currentLocation === locationId)
  }

  function placeName(id) {
    return (unref(entities) || []).find((e) => e.id === id)?.name || id
  }

  // Scene scope: the current location only — its parents and zones are drawers,
  // not part of the roster (the human's call).
  const sceneEntitiesHere = computed(() =>
    occupants.value.filter((e) => e.currentLocation === unref(currentLocationId))
  )

  // Parents: the ancestor chain, nearest first (the universe is the last step).
  const sceneParentGroups = computed(() => {
    const here = unref(currentLocationId)
    const path = []
    if (!findAncestorIds(unref(locationTree), here, path)) return []
    return path
      .filter((id) => id !== here)
      .reverse()
      .map((id) => ({ id, name: placeName(id), entities: entitiesAt(id) }))
  })

  // Zones: the current location's sub-locations, in tree order.
  const sceneZoneGroups = computed(() => {
    const node = findTreeNode(unref(locationTree), unref(currentLocationId))
    return (node?.children || []).map((c) => ({
      id: c.id, name: c.name, entities: entitiesAt(c.id),
    }))
  })

  return { occupants, sceneEntitiesHere, sceneParentGroups, sceneZoneGroups }
}

// The ancestor walk reads the tree by id: `path` comes back **root-first and
// including the node itself**, which is `useLocationTree`'s contract and what
// the `.reverse()` below is written against. Kept here (rather than imported)
// because it is a pure tree read with no state: this composable must not take a
// dependency on the panel's tree state to answer a question about a tree it was
// handed.
function findAncestorIds(nodes, targetId, path) {
  for (const n of (nodes || [])) {
    path.push(n.id)
    if (n.id === targetId) return true
    if (n.children && findAncestorIds(n.children, targetId, path)) return true
    path.pop()
  }
  return false
}
