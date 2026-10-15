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
 * The tag that marks a container whose contents are an **authored sequence**.
 *
 * The author's mark, deliberately not an inference. `order` is optional and
 * almost nothing uses it — 11 of 926 live sub-trait settings carry one, all of
 * them portents — so "some child has an `order`" would make the sheet's shape a
 * side effect of stray data entry, and a container whose children happen to be
 * numbered would silently stop reading as the bag it is. The tag says the
 * sequence is the point (a portent chain, where the next step is enabled by the
 * one before it), and the sheet then has to make the sequence legible instead of
 * packing the rows as chips.
 *
 * Rides the same union as `container` itself (registry ∪ instance, B116), so it
 * can be set on the definition or on a single instance.
 */
export const ORDERED_TAG = 'ordered'

/**
 * The depth the sheet's entity query selects, in levels. Keep in step with the
 * `TraitNodeDepth*` fragment chain in CharacterSheet.vue.
 */
export const QUERY_DEPTH = 4

/** A setting's children, exactly as nested by the API. */
export function childrenOf(setting) {
  return setting?.subTraitSettings || []
}

/**
 * A setting's children in the author's order — what the sheet *renders*.
 *
 * The sub-trait reads already sort by `order` (`order == null, order,
 * traitset_id, trait_id, _key`), so today this returns what `childrenOf` returns.
 * It exists so the sheet's rendering does not *depend* on a read it does not own:
 * the detail panel and the editor reach settings by other routes, and the
 * container drag still has to land somewhere predictable. A partly-ordered set
 * degrades exactly as the reads do — ordered children first, the unordered
 * remainder after them, stable by their query position.
 */
export function orderedChildren(setting) {
  const kids = childrenOf(setting)
  if (!kids.some((k) => typeof k?.order === 'number')) return kids
  const rank = (k) => (typeof k?.order === 'number' ? k.order : Number.MAX_SAFE_INTEGER)
  return kids
    .map((k, i) => ({ k, i }))
    .sort((a, b) => (rank(a.k) - rank(b.k)) || (a.i - b.i))
    .map((entry) => entry.k)
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

/**
 * Whether a container's contents are an **ordered list** rather than a bag.
 *
 * Requires the container tag as well as `ordered`: the tag describes how to
 * render a set of children, and a trait with no children has no list to order,
 * so `ordered` alone would be a mark with nothing to mark. See `ORDERED_TAG`
 * for why this is a tag and not an inference from `order`.
 */
export function isOrdered(trait) {
  return isContainer(trait) && traitTags(trait).includes(ORDERED_TAG)
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

/**
 * Trait definitions in the order a picker should read: alphabetical by the name
 * the reader is scanning for.
 *
 * The registry's own order is arbitrary — `traitsByUniverse(earth)` comes back
 * `regime alert`, `technology`, `size`, `hydrography`, … — so a picker showing it
 * raw is the one list on the sheet that cannot be scanned for a name you already
 * have in mind (the author, 2026-09-29: *"I want the trait list sorted when I want
 * to add a trait"*). The trait **sets** above it are already ordered by their own
 * `order`, and the definition picker in the editor already reads alphabetically,
 * so this is the add picker falling in with both.
 *
 * Case-insensitive (`sensitivity: 'base'`), so `fire blade` and `Fire Blade` do
 * not sort into two runs, and settled on the id so two names that compare equal
 * still land in a fixed order — the same discipline the entity lists use.
 */
export function sortTraitDefinitions(definitions) {
  return [...(definitions || [])].sort((a, b) =>
    String(a?.name || '').localeCompare(String(b?.name || ''), undefined, { sensitivity: 'base' })
    || String(a?.id || '').localeCompare(String(b?.id || '')))
}

/**
 * The row that **heads** each run of rows about one relationship, and the label it
 * carries.
 *
 * Consecutive rows about the same relationship are one group, and the group states
 * whom the relationship concerns once — at its top, as a header, with its traits
 * under it. That is the rule the Blue Book applies to consecutive entries from one
 * sender (`entryContinuations`), taken one step further: the name is not a marker
 * on a line, it names the block.
 *
 * **Why a header rather than `→ name` on the first row** (the shape this replaced,
 * `relationContinuations`): the marker moved with the run's order, and nothing
 * pinned that order. `sortSetTraits` is a stable sort on rank alone, so the
 * tiebreak is the order the API returned the settings in — and within one edge
 * that order is not defined (measured on `character-20809`: the two settings of
 * edge `26767096` come back `…:trait-62763626` then `…:trait-338957761`, the
 * *opposite* of their key order). Whichever row was drawn first stated the
 * contact, so a trait could stop showing its relationship — and did, to the
 * author, who read it as the notes edit having dropped it (2026-09-29). A header
 * per group cannot move: every relationship states its contact, exactly once,
 * whichever of its rows happens to be drawn first.
 *
 * Returns a `Map` from row id to the head that row should draw. A row that does
 * not start a group is absent from it, and so is a row that is not a relationship
 * row — or one whose contact has no name, since a header reading `→ gmc-1234`
 * would be worse than the marker it replaces.
 *
 * The relationship's identity is its contact **and** its edge type: one entity can
 * be both a place you have a `relation` with and a faction you hold `membership`
 * in, and those are two different relationships that happen to share a contact.
 */
export function relationGroups(traits) {
  const heads = new Map()
  let run = null // the key the rows currently being read belong to
  for (const t of (traits || [])) {
    const contact = t?.fromType === 'relationship' ? t.relationshipContactId : null
    const named = !!contact && !!t.relationshipContactName
    const key = named ? `${contact}|${t.relationshipType || ''}` : null
    if (!key) { run = null; continue }
    if (run === key) continue // the same run — its head is already set
    run = key
    heads.set(t.id, {
      name: t.relationshipContactName,
      type: t.relationshipType || '',
      // The id, so a host can make the header a way to the contact's sheet
      // without re-deriving which entity the group is about.
      contactId: contact,
    })
  }
  return heads
}

/**
 * Pull rows about the same relationship together, so a group is consecutive.
 *
 * Rows are ordered by their setting id, which begins with the edge key — so two
 * traits on **one** relationship are adjacent, and two on **different edges to the
 * same contact** are not. That second case is real: the same pair can carry an
 * entity-level edge and a body-level one, and the reader sees one relationship
 * either way. Without this, `relationContinuations` would only ever fire on data
 * that was authored in one go.
 *
 * Stable by first appearance: a relationship keeps the place its first row had,
 * and its remaining rows follow it. Anything that is not a relationship row keeps
 * its own position, so this is a no-op for every other set.
 */
export function groupRelationRows(traits) {
  const groups = new Map()
  for (const t of traits || []) {
    const key = t?.fromType === 'relationship' && t.relationshipContactId
      ? `rel:${t.relationshipType || ''}:${t.relationshipContactId}`
      : `row:${t?.id}`
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(t)
  }
  return [...groups.values()].flat()
}
