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

/** Every setting under this one, at any depth, depth-first. */
export function descendantsOf(setting) {
  const out = []
  for (const child of childrenOf(setting)) out.push(child, ...descendantsOf(child))
  return out
}

/**
 * The chain of parents above a sub-trait, **root-first**.
 *
 * A sub-trait has no anchor of its own, so playing one completes the pick by
 * bringing its chain in. `nodes` is the search space (the sheet's effective and
 * all-trait lists); the walk is cycle-guarded so a malformed parent link cannot
 * hang it.
 */
export function ancestorsOf(setting, nodes) {
  const chain = []
  const seen = new Set([setting.id])
  let cur = setting
  while (cur && cur.fromType === 'traitsetting' && cur.parentTraitsettingId) {
    const parent = findSetting(nodes, cur.parentTraitsettingId)
    if (!parent || seen.has(parent.id)) break
    seen.add(parent.id)
    chain.unshift(parent)
    cur = parent
  }
  return chain
}

/**
 * The negative sub-traits a trait **carries** — the ones a group play pushes
 * alongside it. Static only: a resource or challenge sub-trait is *spent*, and
 * spending is the player's deliberate act, not a side effect of its parent.
 */
export function carriedNegatives(setting) {
  return childrenOf(setting).filter(child =>
    child?.polarity === 'NEGATIVE' && child?.ratingType === 'STATIC')
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

/** Find a setting by id anywhere in a list of trees. */
export function findSetting(nodes, id) {
  for (const setting of nodes || []) {
    if (setting.id === id) return setting
    const hit = findSetting(childrenOf(setting), id)
    if (hit) return hit
  }
  return null
}

/**
 * The top-level setting that anchors a trait's chain — the setting a sub-trait
 * ultimately hangs from. `null` if the chain is not in `nodes`.
 *
 * Mirrors `_resolve_ego` on the backend: a sub-trait has no anchor of its own,
 * so anything derived from the anchor comes from the root of its chain.
 */
export function rootAnchor(nodes, settingId) {
  let cur = findSetting(nodes, settingId)
  const seen = new Set()
  while (cur && cur.fromType === 'traitsetting' && cur.parentTraitsettingId) {
    if (seen.has(cur.id)) return null
    seen.add(cur.id)
    cur = findSetting(nodes, cur.parentTraitsettingId)
  }
  return cur || null
}

/**
 * Which rows can be picked up with a grip.
 *
 * Two kinds, and the second is now **recursive**:
 *   - a **root** trait (`depth === 0`);
 *   - a trait sitting **inside a container**, at *any* depth, so it can be
 *     pulled back out.
 *
 * A sub-trait of a NON-container stays put however deep it is: it is part of its
 * parent, not a thing the container holds. So the rule is about the **parent**,
 * not about the depth — which is the shape the human's 2026-09-13 correction was
 * reaching for ("a sub-trait of a sub-trait is part of its parent and never
 * moves"); the depth cap that came with it was incidental, and it is what hid
 * the Iron Roots third level, where `portents` holds `portents` holds `portents`
 * and only the middle one could be picked up.
 *
 * `hasDestination` — some open container that is neither this row nor inside it —
 * applies at every depth, and is what keeps the cycle case (a container dropped
 * into its own descendant) out of the UI at any level, mirroring the backend's
 * `_would_cycle`. For a nested row it is normally its own parent.
 */
export function canPickUp({ depth = 0, insideContainer = false, hasDestination = false } = {}) {
  return (depth === 0 || insideContainer) && hasDestination
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
 *
 * `insideContainer` adds the rule for a row that is *itself* container contents:
 * its sub-traits are part of it and stay hidden, because the container is the
 * thing you are looking into. **A container nested inside a container is the
 * exception** — it is a pick in its own right and its row renders a disclosure,
 * so suppressing its children leaves a chevron that opens nothing. That was a
 * live dead control on the Iron Roots faction, whose `portents` container holds
 * another `portents` container three levels down: the deeper contents existed,
 * were fetched, and could never be reached.
 */
export function showsChildren(trait, { rootKnown = true, expanded = false, insideContainer = false } = {}) {
  if (childrenOf(trait).length === 0) return false
  if (!rootKnown) return false
  if (insideContainer && !isContainer(trait)) return false
  return !isContainer(trait) || expanded
}

/**
 * A set's traits: ego first, morph after, containers last.
 *
 * Ego traits are what the character *is* — they travel between bodies; a morph
 * trait belongs to one body and changes when the projection does. Reading
 * self → body → furniture separates the two instead of interleaving them, which
 * matters because most sets mix them heavily (``distinctions`` carries 878 morph
 * settings against 66 ego ones). A container holds rather than acts — no die to
 * play — so it sits under both, ego containers still above morph ones.
 *
 * Stable: each group keeps the order the query returned, so nothing else moves.
 */
export function sortSetTraits(traits) {
  // 0 ego · 1 morph · +2 when it is a container
  const rank = (t) => (isContainer(t) ? 2 : 0) + (t?.ego === false ? 1 : 0)
  return (traits || [])
    .map((t, i) => ({ rank: rank(t), i, t }))
    .sort((a, b) => (a.rank - b.rank) || (a.i - b.i))
    .map(entry => entry.t)
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

/**
 * The **unfilled** dice of a challenge track, in track order.
 *
 * `capacity` is the pool's target (positive) or ceiling (negative) — e.g.
 * `[D6, D6, D6]` — and `dice` is what the ledger has filled toward it, so the
 * shortfall is the *tail* of the capacity array. Slice rather than synthesize:
 * live capacities are mixed-type (`['d8','d8','d6']`), and an unfilled slot has
 * its own type.
 *
 * The shortfall is deliberately **not** paired with the filled dice. The two
 * lists are independent — a `d6` can fill a `d8` slot — and pairing them would
 * invent an alignment the data does not carry. The sheet shows the filled dice
 * as themselves and the shortfall as the capacity it is.
 */
export function challengeRemaining(setting) {
  if (!setting || setting.ratingType !== 'CHALLENGE') return []
  const capacity = setting.capacity || []
  const filled = (setting.dice || []).length
  return filled >= capacity.length ? [] : capacity.slice(filled)
}

/**
 * The trait count at which the sheet stops showing one flat list and starts
 * splitting by trait set. From [[Troupe Play]] § *Sheet & base difficulty* (B60):
 * a list layer that only ever holds an entry or two is a click that buys
 * nothing, so a low-trait entity skips it; a high-trait one needs it.
 */
export const FLAT_TRAIT_LIMIT = 12

/**
 * Whether the Traits tab shows **one flat list** rather than the trait-set layer.
 *
 * Counts the traits that tab would list — the roots of `traitSets`, which already
 * excludes profile traits: those render on their own tab and `recomputeTraitSets`
 * keeps them out of the sets entirely. So the profile half never moves this
 * threshold, which is the rule the human asked for.
 *
 * Nested sub-traits do **not** count. They ride their parent rather than being
 * picks of their own (the same distinction `countSetPicks` makes), so a single
 * trait carrying a dozen details is still one trait to look at.
 */
export function usesFlatTraitList(traitSets, limit = FLAT_TRAIT_LIMIT) {
  const roots = (traitSets || []).reduce((n, ts) => n + (ts?.traits?.length || 0), 0)
  return roots <= limit
}
