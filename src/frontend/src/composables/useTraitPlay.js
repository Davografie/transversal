/**
 * Playing a trait — one implementation, wherever a trait is drawn.
 *
 * "Play" means the same thing on a character sheet and on a location's map chip:
 * the trait's rating goes into the roll, or a RESOURCE/CHALLENGE pool gives up a
 * die. The *semantics* are what must not drift, because they are fiddly and have
 * been tuned:
 *
 *  - **The gates.** Nothing is played unless the roller is in `adding` (never
 *    mid-roll) and the trait is not disabled.
 *  - **The single-vs-mixed split.** A row click spends only when the pool holds a
 *    single die type; a mixed pool is spent per die group, from its own buttons. So
 *    a mixed pool's row click deliberately does nothing rather than guessing.
 *  - **The pool payload.** A multi-die trait contributes one pool die per rating
 *    entry (a `dice` array); a single die contributes a `die`. Negativity rides the
 *    payload so the dice layer can route it to the opposition.
 *  - **The group.** A trait is never played alone: `cascade` completes (or
 *    dismantles) the group around it first, and it pushes the group's own members
 *    through **this module's** `contribute`, so a group member's payload is shaped
 *    here too.
 *
 * Everything a host genuinely differs on is injected. The sheet supplies its pool
 * bookkeeping (which traits are in the pool, refund tracking, the just-picked
 * highlight); the location viewer supplies none of that and a no-op instead.
 *
 * @param {object}   host
 * @param {Function} host.phase            getter — the roller's phase ('adding' = playable)
 * @param {Function} host.cascade          (t, api) => void|Promise; `api.contribute` and
 *                                         `api.canPlay` are the shared ones, so group
 *                                         members are pushed by this module
 * @param {Function} host.addToPool        (payload) => void — hand dice to the roller
 * @param {Function} [host.notePick]       (tsId) => void — the host's "just picked" hint
 * @param {Function} [host.displayName]    (name) => string for the pool's source label
 * @param {Function} [host.armedSfxIdsFor] (t) => string[] — SFX armed this roll
 * @param {Function} host.spendResourceDie async (tsId, dieType) => Promise
 * @param {Function} host.spendChallengeDie async (tsId, dieType, destination) => Promise
 * @param {Function} [host.rememberSpend]  (tsId, { die, kind }) => void — refund bookkeeping
 * @param {Function} [host.refresh]        async (reason) => void — reload after a spend
 */
export function useTraitPlay(host) {
  const api = {}
  const displayName = host.displayName || traitDisplayName
  const armedSfxIdsFor = host.armedSfxIdsFor || (() => [])
  const notePick = host.notePick || (() => {})
  const rememberSpend = host.rememberSpend || (() => {})

  /** Whether playing this trait would do anything at all. */
  function canPlay(t) {
    return host.phase() === 'adding' && t.enabled !== false
  }

  /** The distinct die types in a pool, lowercased. */
  function dieTypes(t) {
    return [...new Set((t.dice || []).map(d => (typeof d === 'string' ? d.toLowerCase() : d)))]
  }

  /**
   * Push one trait's rating into the pool. The trait's own dice only — the group
   * around it is `cascade`'s business.
   */
  function contribute(t) {
    const dice = (t.dice || []).map(d => (typeof d === 'string' ? d.toLowerCase() : d))
    if (!dice.length) return  // no die rating — nothing to add
    notePick(t.id)
    const payload = {
      source: t.name,
      label: displayName(t.name),
      tsId: t.id,
      negative: t.polarity === 'NEGATIVE',
      armedSfxIds: armedSfxIdsFor(t),
    }
    // Multi-die traits contribute one pool die per rating entry.
    if (dice.length > 1) host.addToPool({ ...payload, dice })
    else host.addToPool({ ...payload, die: dice[0] })
  }

  /** Spend one die of the chosen type from a resource and add it to the pool. */
  async function spendResourceGroup(t, dieType) {
    if (!canPlay(t)) return
    await host.spendResourceDie(t.id, dieType)
    rememberSpend(t.id, { die: dieType, kind: 'resource' })
    notePick(t.id)
    host.addToPool({
      die: dieType, source: t.name, label: displayName(t.name), tsId: t.id,
      negative: t.polarity === 'NEGATIVE', resource: true, armedSfxIds: armedSfxIdsFor(t),
    })
    if (host.refresh) await host.refresh('resource-spend')
  }

  /**
   * Spend one die from a challenge pool and route it per polarity: negative (doom)
   * → destination "opposition" (a plain die, routed to the opposition); positive
   * (progress) → destination "pool" (a flagged resource, joins its owner's pool).
   */
  async function spendChallengeGroup(t, dieType) {
    if (!canPlay(t)) return
    const destination = t.polarity === 'NEGATIVE' ? 'opposition' : 'pool'
    const res = await host.spendChallengeDie(t.id, dieType, destination)
    if (!res) return
    t.dice = (res.dice || []).map(d => d.toUpperCase())
    // Only a die that lands in an editable pool can be pulled back out again — a doom
    // die routed to the opposition/difficulty pool is tracked by nobody here, and
    // treating it as "missing from my own pool" would refund it while it is
    // legitimately sitting in the difficulty pool.
    if (res.resource) rememberSpend(t.id, { die: res.die.toLowerCase(), kind: 'challenge' })
    notePick(t.id)
    host.addToPool({
      die: res.die.toLowerCase(), source: t.name, label: displayName(t.name), tsId: t.id,
      negative: t.polarity === 'NEGATIVE', resource: res.resource, armedSfxIds: armedSfxIdsFor(t),
    })
    if (host.refresh) await host.refresh('challenge-spend')
  }

  /** The row click: complete the group, then play or spend. */
  async function playTrait(t) {
    if (!canPlay(t)) return
    // Complete (or dismantle) the group before the clicked trait's own dice.
    await host.cascade(t, api)

    if (t.ratingType === 'RESOURCE') {
      const types = dieTypes(t)
      if (types.length === 1) await spendResourceGroup(t, types[0])
      return
    }
    if (t.ratingType === 'CHALLENGE') {
      const types = dieTypes(t)
      if (types.length === 1) await spendChallengeGroup(t, types[0])
      return
    }
    contribute(t)
  }

  // Exposed to the host's `cascade`, so a group member is pushed by this module
  // rather than by a second copy of the payload shape.
  Object.assign(api, { contribute, canPlay })

  return { playTrait, contribute, canPlay, spendResourceGroup, spendChallengeGroup, dieTypes }
}

/** `some_trait_name` → `Some Trait Name`, for a pool die's source label. */
export function traitDisplayName(name) {
  return String(name ?? '')
    .split('_')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}
