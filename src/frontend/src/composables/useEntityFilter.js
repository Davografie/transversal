import { ref, computed } from 'vue'
import { ENTITY_TYPES } from '@/constants/entityTypes.js'

// Entity filtering and autocomplete for the GM panel. Takes the reactive
// entity list from useEntityCrud and exposes the filter bar state, the
// filtered projections, and the suggestion autocomplete.
export function useEntityFilter(entities) {
  const activeFilters = ref([])
  const filterInput = ref('')
  const showSuggestions = ref(false)

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

  // A name chip that matches a location or a universe is a *scope* match: the
  // entities at/in it match too. Searching "Yinling Creek" has to show the
  // creek and who is in it — the tree draws occupants, and the location entity
  // alone leaves it with nothing to render.
  const matchedScope = computed(() => {
    const locations = new Set()
    const universes = new Set()
    for (const f of activeFilters.value) {
      if (f.type !== 'name') continue
      for (const e of entities.value) {
        if (e.type !== 'LOCATION' && e.type !== 'UNIVERSE') continue
        if (!(fuzzyMatch(e.name, f.value) || fuzzyMatch(e.id, f.value))) continue
        if (e.type === 'UNIVERSE') universes.add(e.currentUniverse || e.id)
        else locations.add(e.id)
      }
    }
    return { locations, universes }
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
  const suggestions = computed(() => {
    const q = filterInput.value.trim().toLowerCase()
    if (!q) return []
    const results = []
    const seen = new Set()
    for (const u of universes.value) {
      if ((u.key && fuzzyMatch(u.key, q)) || (u.name && fuzzyMatch(u.name, q))) {
        if (!seen.has('uni:' + u.key)) {
          seen.add('uni:' + u.key)
          results.push({ id: 'uni:' + u.key, name: u.name || u.key, entityType: 'UNIVERSE', hint: 'universe', filterType: 'universe', filterValue: u.key, filterLabel: u.name || u.key })
        }
      }
    }
    const types = ENTITY_TYPES
    for (const t of types) {
      if (fuzzyMatch(t, q)) {
        results.push({ id: 'type:' + t, name: t.charAt(0) + t.slice(1).toLowerCase(), entityType: t, hint: 'type', filterType: 'entityType', filterValue: t, filterLabel: t.charAt(0) + t.slice(1).toLowerCase() })
      }
    }
    // Candidates are the whole entity list: chips are additive (OR), so they
    // must not narrow what can be picked — otherwise a name outside the current
    // matches could never be added.
    for (const e of entities.value) {
      if ((fuzzyMatch(e.name, q) || fuzzyMatch(e.id, q)) && !seen.has('ent:' + e.id)) {
        seen.add('ent:' + e.id)
        results.push({ id: 'ent:' + e.id, name: e.name, entityType: e.type, hint: 'name', filterType: 'name', filterValue: e.name, filterLabel: e.name })
      }
    }
    return results.slice(0, 10)
  })

  function selectSuggestion(s) {
    if (s.filterType && s.filterValue) {
      const exists = activeFilters.value.find(f => f.type === s.filterType && f.value === s.filterValue)
      if (!exists) {
        activeFilters.value.push({ type: s.filterType, value: s.filterValue, label: s.filterLabel || s.filterValue })
      }
    }
    filterInput.value = ''
  }

  function hideSuggestions() {
    setTimeout(() => { showSuggestions.value = false }, 150)
  }

  return {
    activeFilters,
    filterInput,
    showSuggestions,
    filteredEntities,
    filteredFactions,
    sceneEntities,
    suggestions,
    selectSuggestion,
    hideSuggestions,
  }
}
