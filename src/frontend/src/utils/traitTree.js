/**
 * Trait-tree helpers — the shape a trait list takes once nesting is a
 * permission rather than a special case.
 *
 * See [[Container Traits Design Log]]: a *container* is an ordinary trait
 * carrying the `container` tag (registry ∪ instance, per B116). Containers hold
 * other traits, and nesting goes as deep as the data says.
 *
 * These helpers walk the settings exactly as the API nests them —
 * `subTraitSettings` on each setting, one level per selection — rather than
 * building a parallel tree shape. The detail panel and the trait editor read
 * `subTraitSettings` directly, so inventing a second nesting field would only
 * give the codebase two ways to say the same thing.
 *
 * The depth is bounded by the query: GraphQL needs every level spelled out, so
 * the sheet asks for QUERY_DEPTH levels (see the chained fragments on `QUERY` in
 * CharacterSheet.vue). Raising QUERY_DEPTH without raising the query — or the
 * reverse — silently truncates or over-fetches.
 */

/** The tag that marks a trait as a container. */
export const CONTAINER_TAG = 'container'

/**
 * The depth the sheet's entity query selects, in levels. Keep in step with the
 * `TraitNodeDepth*` fragment chain in CharacterSheet.vue.
 */
export const QUERY_DEPTH = 4

/** A setting's children, exactly as nested by the API. */
export function childrenOf(setting) {
  return setting?.subTraitSettings || []
}

/** A setting's own tags plus its registry trait's, deduped (B116). */
export function traitTags(trait) {
  return [...new Set([...(trait?.tags || []), ...(trait?.registryTags || [])])]
}

/** Whether a trait is a container — i.e. holds other traits. */
export function isContainer(trait) {
  return traitTags(trait).includes(CONTAINER_TAG)
}

/** How many traits sit under this one, at any depth (a container's contents count). */
export function countDescendants(setting) {
  return childrenOf(setting).reduce((n, child) => n + 1 + countDescendants(child), 0)
}

/**
 * A container with contents — the only kind that earns a disclosure control.
 *
 * An *empty* container must not show one: the chevron would open nothing, which
 * is a dead affordance, and a container is empty by default the moment it is
 * tagged. Without this, tagging a trait every character already holds turns
 * every one of those rows into a control that does nothing.
 */
export function hasContents(trait) {
  return isContainer(trait) && childrenOf(trait).length > 0
}

/**
 * A container is "open" for arranging when it is expanded — or when it is empty.
 *
 * An empty container has nothing to hide, and it is the state you most want to
 * drop into. Requiring a disclosure tap to reach it would deadlock: an empty
 * container has no disclosure (a chevron opening nothing is a dead control), so
 * it could never be opened, so nothing could ever be dropped into it.
 */
export function isOpenContainer(trait, expanded = false) {
  if (!isContainer(trait)) return false
  return expanded || childrenOf(trait).length === 0
}

/** Whether `id` is `root` itself or sits anywhere beneath it. */
export function subtreeContains(root, id) {
  if (!root) return false
  if (root.id === id) return true
  return childrenOf(root).some((child) => subtreeContains(child, id))
}

/**
 * Whether a row should render its children.
 *
 * A non-container always shows its sub-traits — they are part of it, which is
 * also why they do not count separately against the set's limit. A container
 * shows them only once it has been opened, because its children are picks in
 * their own right and there may be many of them.
 *
 * `rootKnown` carries the fog-of-war answer for the row itself: a nested row
 * inherits its root's, since sub-traits have never been gated individually.
 */
export function showsChildren(trait, { rootKnown = true, expanded = false } = {}) {
  if (childrenOf(trait).length === 0) return false
  if (!rootKnown) return false
  return !isContainer(trait) || expanded
}

/**
 * What a set's `limit` counts, now that traits nest.
 *
 * `limit` counts *pool picks*, not ownership. Sub-traits are part of their
 * parent, so a non-container contributes 1 however many sub-traits ride along.
 * A container contributes its children instead of itself — which is why an
 * empty container costs nothing, and why a container never enters the pool on
 * its own (it carries no die to play).
 *
 *     picks(node) = node is container
 *                     ? sum(picks(child) for every child)
 *                     : (anything in this subtree in the pool ? 1 : 0)
 */
export function countSetPicks(settings, isInPool) {
  return (settings || []).reduce((n, setting) => n + countPicks(setting, isInPool), 0)
}

function countPicks(setting, isInPool) {
  if (isContainer(setting)) {
    return childrenOf(setting).reduce((n, child) => n + countPicks(child, isInPool), 0)
  }
  return subtreeTouched(setting, isInPool) ? 1 : 0
}

function subtreeTouched(setting, isInPool) {
  if (isInPool(setting)) return true
  return childrenOf(setting).some((child) => subtreeTouched(child, isInPool))
}
