/**
 * Dice spent out of a trait into the dice pool — and what to do when the pool
 * drops them again.
 *
 * A die spent into a still-assembling pool that is then pulled back out (chip
 * click in the DiceRoller) never reached a roll, so it belongs to its trait
 * again. `kind` picks the path back:
 *
 *   - `'resource'` → the trait keeps a spent ledger, so the die returns
 *     through it (`recoverResourceDie`).
 *   - `'challenge'` → a challenge pool has no ledger, so the die is refunded
 *     outright (`recoverChallengeDie`).
 */

/**
 * Split tracked entries into the ones the pool still holds and the ones it let
 * go. Matches greedily by die type, so spending two d6s and removing one
 * refunds exactly one.
 *
 * @param {Array<{die: string, kind: string}>} entries  tracked spends for one trait
 * @param {string[]} poolDice  that trait's dice currently in the pool
 * @returns {{ keep: Array, refunds: Array }}
 */
export function splitRefunds(entries, poolDice) {
  const unclaimed = [...(poolDice || [])]
  const keep = []
  const refunds = []
  for (const entry of entries || []) {
    const at = unclaimed.indexOf(entry.die)
    if (at !== -1) {
      unclaimed.splice(at, 1)
      keep.push(entry)
    } else {
      refunds.push(entry)
    }
  }
  return { keep, refunds }
}
