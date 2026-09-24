import { ref, computed } from 'vue'
import { ENTITY_TYPES } from '@/constants/entityTypes.js'
import { useCombobox } from '@/composables/useCombobox.js'

// Entity filtering and autocomplete for the GM panel. Takes the reactive
// entity list from useEntityCrud and exposes the filter bar state, the
// filtered projections, and the suggestion autocomplete.
export function useEntityFilter(entities) {
  const activeFilters = ref([])
  const filterInput = ref('')

  // ⚠ Both value AND q must be lowercased. The autocomplete stores the entity's
  // original-cased name as the filter value, but users type lowercase queries.
  function fuzzyMatch(value, q) {
    if (!value || !q) return false
    const raw = value.toLowerCase()
    const ql = q.toLowerCase()
    if (raw.includes(ql)) return true
    const normalized = raw.replace(/_/g, ' ')
    if (normalized.includes(ql)) return true
    const qNormalized = ql.replace(/ /g, '_')
    if (raw.includes(qNormalized)) return true
    return false
  }

  // A location's `currentLocation` is its parent, so the hierarchy the scope
  // needs is derivable from the entity list alone — no tree to thread in. (This
  // composable sits upstream of useLocationTree, which reads the filtered list,
  // so asking the tree here would be a cycle.)
  const locationChildren = computed(() => {
    const childrenOf = new Map()
    for (const e of entities.value) {
      if (e.type !== 'LOCATION' || !e.currentLocation) continue
      if (!childrenOf.has(e.currentLocation)) childrenOf.set(e.currentLocation, [])
      childrenOf.get(e.currentLocation).push(e.id)
    }
    return childrenOf
  })

  // A place covers everything nested under it: searching "Scotland" has to find
  // the people in Craigmuir and The Stag's Head, not only whoever is standing in
  // Scotland itself. Matching the location id exactly left a region whose
  // occupants are all one or two levels down with nothing at all.
  function _withDescendants(rootIds, childrenOf) {
    const out = new Set()
    const stack = [...rootIds]
    while (stack.length) {
      const id = stack.pop()
      if (out.has(id)) continue
      out.add(id)
      for (const c of childrenOf.get(id) || []) stack.push(c)
    }
    return out
  }

  // A name chip that matches a location or a universe is a *scope* match: the
  // entities at/in it match too. Searching "Yinling Creek" has to show the
  // creek and who is in it — the tree draws occupants, and the location entity
  // alone leaves it with nothing to render.
  const matchedScope = computed(() => {
    const universes = new Set()
    const roots = new Set()
    for (const f of activeFilters.value) {
      if (f.type !== 'name') continue
      for (const e of entities.value) {
        if (e.type === 'UNIVERSE') {
          if (fuzzyMatch(e.name, f.value) || fuzzyMatch(e.id, f.value)) universes.add(e.currentUniverse || e.id)
        } else if (e.type === 'LOCATION') {
          if (fuzzyMatch(e.name, f.value) || fuzzyMatch(e.id, f.value)) roots.add(e.id)
        }
      }
    }
    return { locations: _withDescendants(roots, locationChildren.value), universes }
  })

  // Chips combine with OR: an entity matches when it matches *any* active chip
  // — the chips are additive ("show me X, plus Y"), not narrowing. With no
  // chips everything matches.
  function entityMatchesFilters(e) {
    if (!activeFilters.value.length) return true
    return activeFilters.value.some((f) => {
      if (f.type === 'universe') return e.currentUniverse === f.value
      if (f.type === 'entityType') return e.type === f.value
      if (f.type === 'name') {
        if (fuzzyMatch(e.name, f.value) || fuzzyMatch(e.id, f.value)) return true
        const scope = matchedScope.value
        if (e.currentLocation && scope.locations.has(e.currentLocation)) return true
        if (e.currentUniverse && scope.universes.has(e.currentUniverse)) return true
        return false
      }
      return false
    })
  }

  // ── Filtered data ─────────────────────────────────
  const filteredEntities = computed(() => entities.value.filter(entityMatchesFilters))
  const filteredFactions = computed(() => filteredEntities.value.filter(e => e.type === 'FACTION'))
  const sceneEntities = computed(() => filteredEntities.value.filter(e => e.type === 'CHARACTER' || e.type === 'GMC'))
  const universes = computed(() => entities.value.filter(e => e.type === 'UNIVERSE').map(u => ({ key: u.currentUniverse, name: u.name })))

  // ── Autocomplete ──────────────────────────────────
  // The list mechanics (filter, highlight, keyboard, aria) come from the shared
  // combobox; the *filter* semantics stay here — `fuzzyMatch`, the additive-OR
  // chips and the location/universe scope match are what this filter means, not
  // how a suggestion list behaves.
  //
  // Candidates are the whole entity list plus the universe keys and the entity
  // types: chips are additive (OR), so an active chip must not narrow what can
  // be picked — otherwise a name outside the current matches could never be
  // added. Nothing is excluded for already being a chip, which is the long-
  // standing behaviour.
  const candidates = computed(() => {
    const out = []
    const seen = new Set()
    for (const u of universes.value) {
      if (!u.key || seen.has('uni:' + u.key)) continue
      seen.add('uni:' + u.key)
      out.push({
        id: 'uni:' + u.key,
        name: u.name || u.key,
        entityType: 'UNIVERSE',
        hint: 'universe',
        filterType: 'universe',
        filterValue: u.key,
        filterLabel: u.name || u.key,
        terms: [u.key, u.name].filter(Boolean),
      })
    }
    for (const t of ENTITY_TYPES) {
      out.push({
        id: 'type:' + t,
        name: t.charAt(0) + t.slice(1).toLowerCase(),
        entityType: t,
        hint: 'type',
        filterType: 'entityType',
        filterValue: t,
        filterLabel: t.charAt(0) + t.slice(1).toLowerCase(),
        terms: [t],
      })
    }
    for (const e of entities.value) {
      if (seen.has('ent:' + e.id)) continue
      seen.add('ent:' + e.id)
      out.push({
        id: 'ent:' + e.id,
        name: e.name,
        entityType: e.type,
        hint: 'name',
        filterType: 'name',
        filterValue: e.name,
        filterLabel: e.name,
        terms: [e.name, e.id].filter(Boolean),
      })
    }
    return out
  })

  const combo = useCombobox({
    options: candidates,
    query: filterInput,
    allowCustom: false,
    maxResults: 10,
    armTopOnChange: true,
    wrapHighlight: false,        // a picker list, not a tag field
    requireQuery: true,          // an empty box offers nothing, as it always has
    normalize: (o) => ({ value: o.id, label: o.name, hint: o.hint, raw: o }),
    matchTerm: (it, q) => (it.raw.terms || []).some((t) => fuzzyMatch(t, q)),
  })

  const suggestions = computed(() => combo.available.value.map((it) => it.raw))

  function selectSuggestion(s) {
    if (s.filterType && s.filterValue) {
      const exists = activeFilters.value.find(f => f.type === s.filterType && f.value === s.filterValue)
      if (!exists) {
        activeFilters.value.push({ type: s.filterType, value: s.filterValue, label: s.filterLabel || s.filterValue })
      }
    }
    filterInput.value = ''
    // The list is deliberately left open: with an empty box it has nothing to
    // show (`requireQuery`), and it must come back on the next keystroke so
    // several chips can be added in a row — which is how this filter has always
    // behaved.
  }

  // Delayed so a click on a suggestion is not cut short by the input's blur.
  function hideSuggestions() {
    setTimeout(() => combo.closeList(), 150)
  }

  return {
    activeFilters,
    filterInput,
    showSuggestions: combo.open,
    filteredEntities,
    filteredFactions,
    sceneEntities,
    suggestions,
    selectSuggestion,
    hideSuggestions,
    // Keyboard/a11y surface for the filter input.
    highlighted: combo.highlighted,
    moveHighlight: combo.move,
    listId: combo.listId,
    optionId: combo.optionId,
    activeDescendant: combo.activeDescendant,
  }
}
