import { ref } from 'vue'
import { useApi } from '@/composables/useApi.js'

// Every catalog field the wizard *reads* must be selected here: a field missing
// from this selection is one the UI silently treats as absent. `suggest` was
// missing, so a suggestable field (trait tags, SFX names/triggers/source kinds)
// fell back to a plain text box with no autocomplete and no tags editor.
const CATALOG_QUERY = `{
  targetCatalog {
    elements { name label }
    edges { name source targets cardinality label }
    fields { element name type label options operators references suggest }
    aggregations { name label output needsField needsCount accepts }
    collections { name element label singular }
    sourceKinds { value label element variable ownerSurface }
  }
}`

const TRACE_QUERY = `query($input: TargetSpecInput!, $elements: [String!], $cardinality: String, $sourceElement: String, $variables: JSON) {
  traceTargetSpec(input: $input, destinationElements: $elements, destinationCardinality: $cardinality, sourceElement: $sourceElement, variables: $variables) {
    types { element cardinality }
    errors { stepIndex message }
    valid
  }
}`

const VARIABLES_QUERY = `query($effects: [EffectInput!]!, $sourceElement: String, $conditions: [ConditionInput!], $trigger: String, $sourceKind: String) {
  effectVariables(effects: $effects, sourceElement: $sourceElement, conditions: $conditions, trigger: $trigger, sourceKind: $sourceKind) { name element cardinality }
}`

// Module-level singleton: the catalog is shared domain data.
const catalog = ref(null)
const loaded = ref(false)
let pending = null

export function useTargetCatalog() {
  const { graphql } = useApi()

  async function load(force = false) {
    if (catalog.value && !force) return catalog.value
    if (pending) return pending
    pending = graphql(CATALOG_QUERY)
      .then((data) => {
        catalog.value = data?.targetCatalog || null
        loaded.value = !!catalog.value
        return catalog.value
      })
      .finally(() => { pending = null })
    return pending
  }

  // Type-check a spec draft against an optional destination (elements ×
  // cardinality), with an optional source element (for `select source`) and bound
  // variables (name -> element, for `select variable`). `destination.elements` is
  // a list because a field may accept more than one kind of thing — a die in a
  // pool or a die of a trait's rating.
  async function traceSpec(steps, destination, sourceElement = null, variables = null) {
    if (!steps || !steps.length) {
      return { types: [], errors: [], valid: false }
    }
    const data = await graphql(TRACE_QUERY, {
      input: { steps },
      elements: destination?.elements || null,
      cardinality: destination?.cardinality || null,
      sourceElement: sourceElement || null,
      variables: variables || null,
    })
    return data?.traceTargetSpec || { types: [], errors: [], valid: false }
  }

  // Compute the typed names (name -> {element, cardinality}) a list of effects may
  // `select variable` from, for type-hinting. Three sources, in one answer from
  // the backend so the editor never invents a scope of its own:
  //   - the activation's own names (the SFX's trigger variables and its source
  //     token), which the engine binds when the rule fires;
  //   - the SFX's conditions, traced first: their paths run before any effect,
  //     so the names they output are in scope for every effect;
  //   - each effect's own paths, in order (cross-effect).
  async function collectVariables(effects, sourceElement = null, conditions = null, trigger = null, sourceKind = null) {
    const hasScope = trigger || sourceKind
    if ((!effects || !effects.length) && (!conditions || !conditions.length) && !hasScope) return {}
    const data = await graphql(VARIABLES_QUERY, {
      effects: effects || [],
      sourceElement: sourceElement || null,
      conditions: (conditions && conditions.length) ? conditions : null,
      trigger: trigger || null,
      sourceKind: sourceKind || null,
    })
    const map = {}
    for (const v of (data?.effectVariables || [])) {
      if (v?.name && v?.element) map[v.name] = { element: v.element, cardinality: v.cardinality || 'one' }
    }
    return map
  }

  // ── Catalog selectors (pure lookups, no network) ──────────────

  function elementLabel(name) {
    return catalog.value?.elements?.find((e) => e.name === name)?.label || name
  }

  function edgesFrom(element) {
    return (catalog.value?.edges || []).filter((e) => e.source === element)
  }

  function fieldsFor(element) {
    return (catalog.value?.fields || []).filter((f) => f.element === element)
  }

  function aggregations() {
    return catalog.value?.aggregations || []
  }

  function collections() {
    return catalog.value?.collections || []
  }

  function sourceKinds() {
    return catalog.value?.sourceKinds || []
  }

  return { catalog, loaded, load, traceSpec, collectVariables, elementLabel, edgesFrom, fieldsFor, aggregations, collections, sourceKinds }
}
