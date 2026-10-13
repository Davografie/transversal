// Reading an instance's host, and filtering instances — pure, so the check runs them.
//
// A trait *instance* is anchored to one of four things (see the API's
// `services/trait_instance_hosts.py` for the resolution rules): an entity, a
// **body** (a per-universe projection), a **relationship edge**, or another
// instance (a **sub-trait**, which sits under a super-trait). The panel lists
// instances of one definition, so every row has to say who owns it, and the four
// answers read differently enough that the wording belongs in one place.
//
// The line is "whose is it" and the detail is "which one / about whom / under
// what" — kept apart so a row can show them at different weights.

/** The four anchors, in the order a list is grouped by them. */
export const HOST_KINDS = ['entity', 'projection', 'relationship', 'traitsetting']

const KIND_LABELS = {
  entity: 'Entity',
  projection: 'Body',
  relationship: 'Relationship',
  traitsetting: 'Sub-trait',
}

export function hostKindLabel(kind) {
  return KIND_LABELS[kind] || 'Entity'
}

/** Who holds it. Never blank, so a broken row is still identifiable. */
export function hostLine(host) {
  if (!host) return '(unknown host)'
  if (host.kind === 'relationship') {
    const holder = host.entityName || '(gone)'
    return `${holder} → ${host.aboutName || '(gone)'}`
  }
  return host.entityName || '(missing entity)'
}

/** Which body, about whom, under what — the second half of a row's host. */
export function hostDetail(host) {
  if (!host) return ''
  if (host.kind === 'projection') return host.universe ? `in ${host.universe}` : 'body'
  if (host.kind === 'relationship') return host.relationshipType || 'relation'
  if (host.kind === 'traitsetting') return host.parentTraitName ? `under ${host.parentTraitName}` : 'sub-trait'
  return host.entityType || ''
}

/** The entity type, for hosts that name an entity (a body keeps its universe instead). */
export function hostTypeBadge(host) {
  if (!host) return ''
  if (host.kind === 'projection') return ''
  return host.entityType || ''
}

/**
 * Does an instance pass the filter bar? One predicate, so the count, the
 * "select all matching" and the drawn rows can never disagree.
 */
export function instanceMatches(instance, filters = {}) {
  const host = instance?.host || {}
  if (filters.kind && host.kind !== filters.kind) return false
  if (filters.ratingType && instance.ratingType !== filters.ratingType) return false
  if (filters.polarity && instance.polarity !== filters.polarity) return false
  if (filters.die && !(instance.dice || []).includes(filters.die)) return false
  if (filters.enabled === 'yes' && !instance.enabled) return false
  if (filters.enabled === 'no' && instance.enabled) return false

  const q = (filters.q || '').trim().toLowerCase()
  if (!q) return true
  return haystack(instance).includes(q)
}

/** Everything a search should be able to find an instance by. */
export function haystack(instance) {
  const host = instance?.host || {}
  return [
    host.entityName, host.entityType, host.universe,
    host.aboutName, host.relationshipType, host.parentTraitName,
    instance?.statement, instance?.notes,
    ...(instance?.tags || []),
    instance?.id,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
}

/** Grouped by anchor kind, then by who holds it — so a cleanup pass can run a kind at a time. */
export function sortInstances(list) {
  return [...(list || [])].sort((a, b) => {
    const ka = HOST_KINDS.indexOf(a?.host?.kind)
    const kb = HOST_KINDS.indexOf(b?.host?.kind)
    if (ka !== kb) return (ka < 0 ? HOST_KINDS.length : ka) - (kb < 0 ? HOST_KINDS.length : kb)
    const byHost = hostLine(a?.host).localeCompare(hostLine(b?.host))
    if (byHost !== 0) return byHost
    return (a?.statement || '').localeCompare(b?.statement || '')
  })
}

/** How many of each kind, for the filter chips and the "what am I looking at" line. */
export function kindCounts(list) {
  const out = {}
  for (const kind of HOST_KINDS) out[kind] = 0
  for (const instance of list || []) {
    const kind = instance?.host?.kind || 'entity'
    out[kind] = (out[kind] || 0) + 1
  }
  return out
}
