import { ref, computed } from 'vue'
import { entityTypeRank } from '@/constants/entityTypes.js'

// ── Module-level singleton state ─────────────────────
const locationTree = ref([])
const expandedNodes = ref({})
// The node the tree focuses on (the GM's current location in free-roam). While
// set, the tree renders the ancestor chain and collapses each level's other
// children into a single "… N more" stub row — see flattenTree.
const focusId = ref('')

// ── Constants ────────────────────────────────────────
const OCCUPANT_TYPES = new Set(['CHARACTER', 'GMC', 'ASSET'])

export function useLocationTree({ entities, filteredEntities, agencyByEntity, activeFilters, currentUniverse }) {
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

  // `next` is the state the row should move to, which the row knows because it
  // is drawn from the same computation (`expanded` on the flattened node). It
  // cannot be derived here: a level can open *by default* — the current
  // universe, the filter's path, the focus chain — so `expandedNodes[id]` is
  // undefined while the row already reads as open, and toggling that from
  // undefined set `true`, a press that did nothing.
  function toggleTreeNode(id, next) {
    const value = next === undefined ? !expandedNodes.value[id] : next
    expandedNodes.value = { ...expandedNodes.value, [id]: value }
  }

  // ── Occupant grouping ──────────────────────────────
  // The tree reads the way the sheet's relationship list does: mains first, then
  // supports, then everyone else by type, alphabetical inside each group. The
  // name tiebreak is what makes the order *deterministic* rather than merely
  // grouped — the entity list arrives unsorted (`list_all_entities` has no
  // SORT), and a stable sort preserves that arbitrary order within a type. The
  // id is the last resort so two names that compare equal (they differ only in
  // case, which `sensitivity: 'base'` ignores) still land in a fixed order.
  function _sortOccupants(arr) {
    const agency = agencyByEntity?.value
    const byName = { sensitivity: 'base' }
    arr.sort((a, b) =>
      (entityTypeRank(a.type, agency?.get(a.id)) - entityTypeRank(b.type, agency?.get(b.id)))
      || String(a.name || '').localeCompare(String(b.name || ''), undefined, byName)
      || String(a.id).localeCompare(String(b.id)))
  }

  // Both rosters are needed. `occupantsByLocation` is what the filter matches,
  // and is what a level reveals on its own; `allOccupantsByLocation` is everyone
  // who is actually there, which is what tells the chevron whether the filter is
  // hiding people. With only the filtered one, a place whose occupants all failed
  // the filter looked empty — so the roster check passed vacuously and the level
  // claimed ▾ while hiding its whole roster.
  function _groupOccupants(list, placed) {
    const map = {}
    for (const e of list) {
      if (!OCCUPANT_TYPES.has(e.type)) continue
      // Placed and unplaced are disjoint halves, and the halves are what the
      // group key means: a placed occupant belongs to a location, an unplaced one
      // to a universe. Requiring the *right* one matters — grouping the unplaced
      // on `currentUniverse` alone lists everybody in that universe, placed or
      // not, which is how a universe node came to show the whole roster.
      // (The app's own `UNPLACED` condition is `current_location in (None, "")`.)
      if (placed ? !e.currentLocation : e.currentLocation) continue
      const key = placed ? e.currentLocation : e.currentUniverse
      if (!key) continue
      if (!map[key]) map[key] = []
      map[key].push(e)
    }
    for (const key of Object.keys(map)) _sortOccupants(map[key])
    return map
  }

  const occupantsByLocation = computed(() =>
    _groupOccupants(filteredEntities?.value ?? [], true))
  const allOccupantsByLocation = computed(() =>
    _groupOccupants(entities?.value ?? filteredEntities?.value ?? [], true))

  const unplacedByUniverse = computed(() =>
    _groupOccupants(filteredEntities?.value ?? [], false))
  const allUnplacedByUniverse = computed(() =>
    _groupOccupants(entities?.value ?? filteredEntities?.value ?? [], false))

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

  // `occupants` / `allOccupants` are the matched and the full rosters; the
  // difference is what the filter is hiding, which the chevron has to own up to.
  // `forced` = this level's nodes are being shown because their parent was
  // explicitly expanded, so the filter's populated-path prune must not drop
  // them again. That is precisely what was missing: pressing ▸ on a filtered
  // level flipped the chevron to ▾ and revealed nothing, because the children
  // it recursed into were pruned one frame later.
  function flattenTree(nodes, occupants, allOccupants, depth = 0, forced = false) {
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
      if (filterMode && !onPath && !forced) continue
      const onFocus = focusMode && focusSet.has(node.id)

      const kids = node.children || []
      // `occ` is who the filter matched here; `allOcc` is everyone who is here.
      // The chevron has to answer to the second one — otherwise a place whose
      // occupants all failed the filter looks empty, the roster check passes
      // vacuously, and the level claims ▾ while hiding its entire roster.
      const occ = occupants[node.id] || []
      const allOcc = allOccupants[node.id] || []
      const unplacedHere = kind === 'universe' && node.universe
        ? (unplacedByUniverse.value[node.universe] || [])
        : []
      const allUnplacedHere = kind === 'universe' && node.universe
        ? (allUnplacedByUniverse.value[node.universe] || [])
        : []

      // What this level reveals *on its own*, before the GM touches the chevron:
      // the filter's populated path, the focus chain's on-chain child, or — in
      // the plain view — the current universe's roots. Nothing else opens
      // itself, so a plain location shows no children until it is opened.
      let defaultKids = []
      let defaultRoster = false
      let defaultUnplaced = false
      let baselineOpen = false
      if (filterMode) {
        defaultKids = kids.filter((c) => populated.has(c.id))
        defaultRoster = occ.length > 0
        baselineOpen = true      // being on the populated path is this mode's baseline
      } else if (focusMode) {
        defaultKids = onFocus ? kids.filter((c) => focusSet.has(c.id)) : []
        defaultRoster = occ.length > 0 && node.id === focusId.value
        baselineOpen = onFocus
      } else {
        baselineOpen = depth === 0 && node.universe === curUniverse
        defaultKids = baselineOpen ? kids : []
        defaultUnplaced = baselineOpen
      }

      // Pressing ▾ has to hide something. It returns the level to its baseline
      // when that baseline hides part of the level (the filter's path, the focus
      // chain); where the baseline *is* everything — the plain view's current
      // universe, or a filter that happens to match every child — "back to the
      // baseline" would be a press that does nothing, so it hides the lot.
      // Compared against the FULL rosters: people the filter dropped are hidden
      // content, and hiding them is what ▸ is for.
      const baselineHides =
        defaultKids.length < kids.length ||
        (allOcc.length > 0 && !defaultRoster) ||
        (allUnplacedHere.length > 0 && !defaultUnplaced)
      const explicit = expandedNodes.value[node.id]
      const revealAll = explicit === true
      const hideAll = explicit === false && !baselineHides

      const revealedKids = revealAll ? kids : (hideAll ? [] : defaultKids)
      // An explicit expand shows the whole roster, not only the matched part —
      // the same "press for the rest" the chevron promises for child locations.
      const shownRoster = revealAll ? allOcc : (hideAll ? [] : (defaultRoster ? occ : []))
      const shownUnplaced = revealAll ? allUnplacedHere : (hideAll ? [] : (defaultUnplaced ? unplacedHere : []))
      const contentsOpen = revealAll || (!hideAll && baselineOpen)

      // ▾ means "nothing is left hidden at this level"; ▸ means "press for the
      // rest". A level that shows only part of its children therefore reads ▸,
      // and pressing it is what reveals the others.
      const hasChildren = kids.length > 0 || allOcc.length > 0
      const fullyRevealed = revealedKids.length === kids.length &&
        shownRoster.length === allOcc.length &&
        shownUnplaced.length === allUnplacedHere.length
      result.push({
        id: node.id, name: node.name, universe: node.universe,
        depth, hasChildren, kind,
        expanded: fullyRevealed,
      })
      // In filter mode the matched roster of any place on the path is listed. In
      // focus mode only the focused place itself (and levels the GM expanded by
      // hand) lists occupants — otherwise every ancestor's roster would bloat
      // the chain.
      if (shownRoster.length) {
        for (const e of shownRoster) {
          result.push({
            id: e.id, name: e.name, universe: e.currentUniverse || '',
            depth: depth + 1, hasChildren: false, kind: 'occupant',
            entityType: e.type, entity: e,
          })
        }
        // Occupants live in locations, so the row trails each location's roster.
        if (kind === 'location' && contentsOpen && showAddRows.value) {
          result.push({
            id: 'add:occupant:' + node.id, kind: 'add', addType: 'occupant',
            parentId: node.id, universe: node.universe || '', depth: depth + 1,
            hasChildren: false, name: 'add occupant',
          })
        }
      }
      if (shownUnplaced.length) {
        for (const e of shownUnplaced) {
          result.push({
            id: e.id, name: e.name, universe: e.currentUniverse || '',
            depth: depth + 1, hasChildren: false, kind: 'occupant',
            entityType: e.type, entity: e,
          })
        }
      }
      if (revealedKids.length) {
        // `revealAll` forces this level's children past the filter's prune — the
        // explicit expand the chevron promises.
        result.push(...flattenTree(revealedKids, occupants, allOccupants, depth + 1, revealAll))
      }
      if (focusMode && onFocus) {
        const hidden = kids.length - revealedKids.length
        if (hidden > 0) {
          result.push({
            id: 'more:' + node.id, kind: 'more', parentId: node.id, count: hidden,
            name: `… ${hidden} more`, depth: depth + 1, hasChildren: false,
          })
        }
      }
      // Locations are placed in a universe, so the row trails that universe's
      // children — including when it has none yet.
      if (kind === 'universe' && contentsOpen && showAddRows.value && node.universe) {
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
    return flattenTree(locationTree.value, occupantsByLocation.value, allOccupantsByLocation.value, 0)
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
