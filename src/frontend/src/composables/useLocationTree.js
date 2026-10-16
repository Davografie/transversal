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

// An entity can **carry** a location — an inner world, parented by a `super` edge
// to a character or an object rather than to a place. The tree deliberately does
// not show one (2026-10-16, at the human's direction): a carrier is not a place,
// its `universe` is its *own* and need not be the carried location's, and the
// endpoint reports it as a third kind — `node_type: 'carrier'` — precisely so a
// reader can tell. Dropping the node **and its subtree** here is why the rest of
// the tree can go on treating everything as a universe or a location; the places
// it holds are read and made in the entity panel instead, which opens them as
// child panels. Exported because `check-inner-locations.mjs` drives it.
export function dropCarriers(nodes) {
  return (nodes || [])
    .filter((n) => (n.node_type || n.kind) !== 'carrier')
    .map((n) => (n.children?.length ? { ...n, children: dropCarriers(n.children) } : n))
}

export function useLocationTree({ entities, filteredEntities, agencyByEntity, activeFilters, currentUniverse }) {
  // The focused node: its ancestor chain stays expanded, its siblings stub.
  function setFocus(id) {
    focusId.value = id || ''
  }
  // ── Fetch ──────────────────────────────────────────
  async function fetchLocationTree() {
    try {
      const r = await fetch('/api/v1/locations/tree')
      locationTree.value = dropCarriers(await r.json())
    } catch {
      locationTree.value = []
    }
  }

  // ── The chevron's three modes ───────────────────────
  // `partial` — the reveal a filter or the focus chain puts on screen by itself —
  // is a mode the GM can *choose*, not only one that happens to them. The chevron
  // cycles the three states the row already draws and names:
  //
  //     partial (the filter's path) → expanded (everything) → collapsed (nothing) → partial …
  //
  // and where there is nothing partial to return to — a level whose baseline is
  // either everything or nothing, which is every level in the plain view — it
  // cycles the two that exist, so no press is a press that does nothing. The row
  // says which state that is (`nextReveal` on the flattened node); the store only
  // records the choice.
  //
  // `next` is that state, and it has to come from the row: a level can open *by
  // default* — the current universe, the filter's path, the focus chain — so
  // `expandedNodes[id]` is still undefined while the row already reads as open, and
  // a toggle that read the store would make the first press do nothing.
  //
  // `undefined` in the store means "no choice made — use the baseline", which is
  // what the `partial` mode *is*; so choosing it drops the key rather than storing
  // a third value, and the store stays a tri-state.
  function toggleTreeNode(id, next) {
    if (next === 'partial') {
      const { [id]: _dropped, ...rest } = expandedNodes.value
      expandedNodes.value = rest
      return
    }
    expandedNodes.value = { ...expandedNodes.value, [id]: next === 'expanded' }
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

  // Universes are entities too, so an occupant's `currentLocation` can name the
  // **universe** it is in rather than a place — 54 do (the Discworld set:
  // Rincewind, Cohen, Luggage…, and 20 in Three Realms). That is not a location:
  // such an entity is in the universe but at no place, so it reads under its
  // universe with the unplaced ones rather than being invisible.
  const universeIds = computed(() => new Set(
    (entities?.value ?? filteredEntities?.value ?? [])
      .filter((e) => e.type === 'UNIVERSE')
      .map((e) => e.id)
  ))

  // The GM's drafts, so a row can say so. Unpublished is not occupant-only — 30
  // locations, 6 factions and a universe carry it too — and the tree nodes come
  // from the location endpoint, which does not carry the flag.
  const unpublishedIds = computed(() => new Set(
    (entities?.value ?? filteredEntities?.value ?? [])
      .filter((e) => e.unpublished)
      .map((e) => e.id)
  ))

  // Both rosters are needed. `occupantsByLocation` is what the filter matches,
  // and is what a level reveals on its own; `allOccupantsByLocation` is everyone
  // who is actually there, which is what tells the chevron whether the filter is
  // hiding people. With only the filtered one, a place whose occupants all failed
  // the filter looked empty — so the roster check passed vacuously and the level
  // claimed ▾ while hiding its whole roster.
  function _groupOccupants(list, placed) {
    const map = {}
    const universes = universeIds.value
    for (const e of list) {
      if (!OCCUPANT_TYPES.has(e.type)) continue
      // Placed and unplaced are disjoint halves, and the half is what the group
      // key means: a placed occupant belongs to a location, an unplaced one to a
      // universe. "Unplaced" here is `currentLocation` empty **or naming a
      // universe** — both mean "in this universe, at no place". Requiring the
      // right half matters: keying the unplaced on `currentUniverse` alone lists
      // everybody in that universe, placed or not, which is how a universe node
      // came to show the whole roster.
      const atPlace = !!e.currentLocation && !universes.has(e.currentLocation)
      if (placed !== atPlace) continue
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
  // A chip that selects entities — by type, by name, by status, or by the player
  // holding them — as opposed to a universe chip. The distinction is what the
  // tree's pruning keys off: these chips mean "show the paths to whatever
  // matched" (`filterMode`), while universe chips prune by universe instead, and
  // the two combine as a union.
  const hasEntityChip = computed(() =>
    (activeFilters?.value ?? []).some(f =>
      f.type === 'entityType' || f.type === 'name' || f.type === 'unpublished' ||
      f.type === 'player')
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
    // A place — or a universe — that matched must draw itself even when nothing
    // *inside* it did. Occupants are the only other seed, and a place holding
    // nobody directly (only nested towns) had no populated node on its path at
    // all, so filter mode skipped every row and the tree came back empty. A
    // universe needs it too: filtering for "unpublished" has to reach an
    // unpublished universe with no unpublished descendants.
    if (hasEntityChip.value) {
      for (const e of (filteredEntities?.value ?? [])) {
        if (e.type === 'LOCATION' || e.type === 'UNIVERSE') set.add(e.id)
      }
    }
    // A universe holding matching universe-level occupants is on the populated
    // path too. They are keyed by universe *key* while the nodes carry ids, so
    // this walks the tree rather than seeding the set directly — without it,
    // filtering for Rincewind (who is in Discworld, at no place) marked nothing
    // and the tree came back empty.
    const universeKeys = new Set(
      Object.entries(unplacedByUniverse.value)
        .filter(([, list]) => list.length)
        .map(([key]) => key)
    )
    if (universeKeys.size) {
      const markUniverses = (nodes) => {
        for (const n of nodes) {
          // Only the universe *node* — locations carry the same `universe` key,
          // so matching on it alone marked the whole subtree and filtering for a
          // universe-level occupant unrolled every location in the universe.
          const isUniverse = (n.kind || n.node_type) === 'universe'
          if (isUniverse && n.universe && universeKeys.has(n.universe)) set.add(n.id)
          if (n.children) markUniverses(n.children)
        }
      }
      markUniverses(locationTree.value)
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

  // Inline "add" rows hang off the end of their collection. They used to be
  // offered only while browsing the whole tree — with a filter or a focus the
  // list is a curated subset, so "the end of the collection" is not a stable
  // place to put them. That left **no way to create anything at all** while a
  // chip was active, because these rows are the only create entry point (the
  // author's report, 2026-09-26). The rule is per level now:
  //
  //   * the plain view (no filter, no focus) offers them everywhere, as before;
  //   * a place the filter matched **and its sub-locations** offer them — there
  //     the place *is* the scope the author is working in;
  //   * any level the GM expanded by hand offers them, which is what covers a
  //     filter that names no place (a type, player or status chip) and the focus
  //     chain.
  //
  // `expandedNodes[id] === true` is the explicit expand. `false` is a level the
  // GM closed and `undefined` is one the filter's baseline opened, and neither
  // is the GM saying "work here".
  const filterPlaceIds = computed(() => {
    const ids = new Set()
    if (!hasEntityChip.value) return ids
    // The places the filter matched. `matchedScope` already closes a location
    // chip over its whole subtree, so a sub-location of the filtered place is in
    // this list on its own — which is exactly "the filtered location and its
    // sub-locations".
    for (const e of (filteredEntities?.value ?? [])) {
      if (e.type === 'LOCATION') ids.add(e.id)
    }
    return ids
  })

  // No filter and no focus: the whole tree is on screen and every collection is
  // complete, which is the case the old blanket rule was written for.
  const plainView = computed(() =>
    !hasEntityChip.value && !activeUniverseFilters.value.size && focusPathIds.value.size === 0
  )

  function showsAddRows(node) {
    if (plainView.value) return true
    if (expandedNodes.value[node.id] === true) return true
    return filterPlaceIds.value.has(node.id)
  }

  // `occupants` / `allOccupants` are the matched and the full rosters; the
  // difference is what the filter is hiding, which the chevron has to own up to.
  // `forced` = this level's nodes are being shown because their parent was
  // explicitly expanded, so the filter's populated-path prune must not drop
  // them again. That is precisely what was missing: pressing ▸ on a filtered
  // level flipped the chevron to ▾ and revealed nothing, because the children
  // it recursed into were pruned one frame later.
  function flattenTree(nodes, occupants, allOccupants, depth = 0, forced = false) {
    const result = []
    const filterMode = hasEntityChip.value
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
      if (activeUniverseFilters.value.size > 0 && !hasEntityChip.value) {
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
        // A universe-level occupant that matched is this level's content, the
        // same way a matched roster is a place's — otherwise filtering for one
        // drew its universe with nothing under it.
        defaultUnplaced = unplacedHere.length > 0
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

      // Pressing ▾ has to hide something, and now it always does. It used to
      // return the level to its baseline when the baseline hid part of the level
      // (the filter's path, the focus chain) — which is why a filtered level could
      // never be collapsed: ▾ walked ▾ → ▿ and no further. Collapsing is now
      // *collapsing*; "back to the filter's path" is the `partial` mode, and the
      // chevron reaches it on the next press (the human, 2026-10-13: *"I also want
      // it to be able to collapse when filter is active"*).
      const explicit = expandedNodes.value[node.id]
      const revealAll = explicit === true
      const hideAll = explicit === false

      const revealedKids = revealAll ? kids : (hideAll ? [] : defaultKids)
      // An explicit expand shows the whole roster, not only the matched part —
      // the same "press for the rest" the chevron promises for child locations.
      const shownRoster = revealAll ? allOcc : (hideAll ? [] : (defaultRoster ? occ : []))
      const shownUnplaced = revealAll ? allUnplacedHere : (hideAll ? [] : (defaultUnplaced ? unplacedHere : []))
      const contentsOpen = revealAll || (!hideAll && baselineOpen)

      // Three states, not two. `expanded` is everything on screen, `collapsed` is
      // nothing, and the third is the **partial** reveal a filter or the focus
      // chain puts there on its own — drawn ▿, and now a mode the chevron cycles
      // through rather than one it can only fall back into.
      // The universe-level roster counts as content too: Valhalla has no child
      // locations at all, and its one occupant would otherwise be unreachable.
      const hasChildren = kids.length > 0 || allOcc.length > 0 || allUnplacedHere.length > 0
      const totalContent = kids.length + allOcc.length + allUnplacedHere.length
      const shownContent = revealedKids.length + shownRoster.length + shownUnplaced.length
      const reveal = shownContent === 0 ? 'collapsed'
        : shownContent === totalContent ? 'expanded'
          : 'partial'
      // …and the mode one press from here lands in. Read off the *baseline* — what
      // this level shows with no choice recorded — because that is the only thing
      // between nothing and everything: with a filter or on the focus chain it can
      // be a strict subset, and in the plain view it never is (a level is either
      // fully open at the root or showing nothing).
      const baselineContent = defaultKids.length
        + (defaultRoster ? occ.length : 0)
        + (defaultUnplaced ? unplacedHere.length : 0)
      const baselineReveal = baselineContent === 0 ? 'collapsed'
        : baselineContent === totalContent ? 'expanded'
          : 'partial'
      const nextReveal = reveal === 'partial' ? 'expanded'
        : reveal === 'expanded' ? 'collapsed'
          : (baselineReveal === 'partial' ? 'partial' : 'expanded')
      result.push({
        id: node.id, name: node.name, universe: node.universe,
        depth, hasChildren, kind, reveal, nextReveal,
        unpublished: unpublishedIds.value.has(node.id),
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
            entityType: e.type, entity: e, unpublished: !!e.unpublished,
          })
        }
      }
      // Occupants live in locations, so the row trails each location's roster.
      // It is offered even when the *shown* roster is empty — which is the case a
      // filter creates (nothing here matched it) and the case a brand-new place
      // has always had. Nested inside `shownRoster.length` it used to disappear
      // exactly when a GM needed it most.
      if (kind === 'location' && contentsOpen && showsAddRows(node)) {
        result.push({
          id: 'add:occupant:' + node.id, kind: 'add', addType: 'occupant',
          parentId: node.id, universe: node.universe || '', depth: depth + 1,
          hasChildren: false, name: 'add occupant',
        })
      }
      if (shownUnplaced.length) {
        for (const e of shownUnplaced) {
          result.push({
            id: e.id, name: e.name, universe: e.currentUniverse || '',
            depth: depth + 1, hasChildren: false, kind: 'occupant',
            entityType: e.type, entity: e, unpublished: !!e.unpublished,
          })
        }
      }
      if (revealedKids.length) {
        // `revealAll` forces this level's children past the filter's prune — the
        // explicit expand the chevron promises.
        result.push(...flattenTree(revealedKids, occupants, allOccupants, depth + 1, revealAll))
      }
      // Does this level **end** on a child the GM expanded? The trailing add row
      // then sits one inset step from its parent and below that child's whole
      // subtree, so it reads as if it belonged to the child rather than to this
      // level — the author's report: *"it becomes ambiguous what I'm creating a
      // zone for"*. A child that is only *listed* is fine: the row then reads as
      // the next sibling, which is exactly what it creates.
      //
      // Keyed on the GM's own expand (`expandedNodes[child] === true`), **not** on
      // "the child drew something". A filter draws its path open and a
      // filter-opened level cannot be collapsed — `hideAll` needs a baseline that
      // hides part of the level, which the populated path is not — so measuring
      // from what is on screen would hide the filtered place's row with no way to
      // get it back. Keyed this way, collapsing the child brings the row straight
      // back, which is the escape hatch the rule assumes.
      const lastDrawnChild = revealedKids[revealedKids.length - 1]
      const endsOnExpandedChild = !!lastDrawnChild && expandedNodes.value[lastDrawnChild.id] === true
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
      if (kind === 'universe' && contentsOpen && showsAddRows(node) && node.universe && !endsOnExpandedChild) {
        result.push({
          id: 'add:location:' + node.id, kind: 'add', addType: 'location',
          parentId: node.id, universe: node.universe, depth: depth + 1,
          hasChildren: false, name: 'add location',
        })
      }
      // A location's children are its **zones**, so the same row trails them —
      // this is the tree's way to add to the level the author is looking at,
      // where the entity panel has its own Zones section.
      if (kind === 'location' && contentsOpen && showsAddRows(node) && !endsOnExpandedChild) {
        result.push({
          id: 'add:zone:' + node.id, kind: 'add', addType: 'zone',
          parentId: node.id, universe: node.universe || '', depth: depth + 1,
          hasChildren: false, name: 'add zone',
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
    // Universes are the top level, so their "add" row closes the whole tree. The
    // root is not a node, so it has no place scope to inherit: it offers the row
    // in the plain view, or once the root stub itself has been expanded.
    if (depth === 0 && (plainView.value || expandedNodes.value[ROOT_KEY] === true)) {
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
