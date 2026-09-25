/**
 * check-trait-play.mjs — "playing a trait" means the same thing everywhere.
 *
 * `useTraitPlay` took the sheet's play rules so a map chip and a sheet row cannot
 * drift. That refactor is the risk this file exists for: the rules are fiddly and
 * were tuned in place — the gates, the single-vs-mixed die-type split, the pool
 * payload shapes, and the challenge polarity routing.
 *
 * The composable is Vue-free and takes every host effect as a callback, so the whole
 * contract can be driven here with a fake host: no browser, no dependencies. Same
 * convention as the other `check-*.mjs` scripts.
 *
 *   node src/frontend/scripts/check-trait-play.mjs
 */

const { useTraitPlay } = await import('../src/composables/useTraitPlay.js')
const { normalizeLocationTrait } = await import('../src/utils/locationTrait.js')

let fail = 0
const ok = (label, got, want) => {
  const pass = JSON.stringify(got) === JSON.stringify(want)
  if (!pass) fail++
  console.log(`${pass ? '  ok  ' : ' FAIL '} ${label}${pass ? '' : `\n         got ${JSON.stringify(got)}\n        want ${JSON.stringify(want)}`}`)
}

/** A host that records every effect, with a challenge spend that echoes a die back. */
function harness({ phase = 'adding', challengeRes } = {}) {
  const calls = { added: [], spends: [], remembered: [], picks: [], refreshes: [], cascades: [] }
  const play = useTraitPlay({
    phase: () => phase,
    cascade: (t, api) => calls.cascades.push({ id: t.id, canContribute: typeof api.contribute === 'function' }),
    addToPool: (p) => calls.added.push(p),
    notePick: (id) => calls.picks.push(id),
    displayName: (n) => n.toUpperCase(),   // distinctive, to prove the host's is used
    armedSfxIdsFor: () => ['sfx-x'],
    spendResourceDie: async (tsId, die) => calls.spends.push({ kind: 'resource', tsId, die }),
    spendChallengeDie: async (tsId, die, dest) => {
      calls.spends.push({ kind: 'challenge', tsId, die, dest })
      return challengeRes !== undefined ? challengeRes : { dice: ['d6'], die: 'd6', resource: dest === 'pool' }
    },
    rememberSpend: (id, e) => calls.remembered.push({ id, ...e }),
    refresh: async (r) => calls.refreshes.push(r),
  })
  return { play, calls }
}

const static1 = { id: 'ts-1', name: 'population', ratingType: 'STATIC', dice: ['d6'], polarity: 'POSITIVE' }
const static3 = { id: 'ts-2', name: 'regime_alert', ratingType: 'STATIC', dice: ['d6', 'd8', 'd6'], polarity: 'NEGATIVE' }
const resource1 = { id: 'ts-3', name: 'fuel', ratingType: 'RESOURCE', dice: ['d8'], polarity: 'POSITIVE' }
const resourceMixed = { id: 'ts-4', name: 'mixed', ratingType: 'RESOURCE', dice: ['d8', 'd6'], polarity: 'POSITIVE' }
const doom = { id: 'ts-5', name: 'doom', ratingType: 'CHALLENGE', dice: ['d8', 'd8'], polarity: 'NEGATIVE' }
const progress = { id: 'ts-6', name: 'progress', ratingType: 'CHALLENGE', dice: ['d6'], polarity: 'POSITIVE' }

// ── The group is completed first, through the shared contribute ─────────────
{
  const { play, calls } = harness()
  await play.playTrait(static1)
  ok('the group is cascaded before the dice', calls.cascades, [{ id: 'ts-1', canContribute: true }])
  ok('a group member can be pushed by the shared payload shape', calls.cascades[0].canContribute, true)
}

// ── Static: the pool payload ───────────────────────────────────────────────
{
  const { play, calls } = harness()
  await play.playTrait(static1)
  ok('a single die contributes `die`', calls.added, [
    { source: 'population', label: 'POPULATION', tsId: 'ts-1', negative: false, armedSfxIds: ['sfx-x'], die: 'd6' },
  ])
  ok('the host names the pick', calls.picks, ['ts-1'])
}
{
  const { play, calls } = harness()
  await play.playTrait(static3)
  ok('a multi-die trait contributes a `dice` array', calls.added, [
    { source: 'regime_alert', label: 'REGIME_ALERT', tsId: 'ts-2', negative: true, armedSfxIds: ['sfx-x'], dice: ['d6', 'd8', 'd6'] },
  ])
}

// ── The gates ──────────────────────────────────────────────────────────────
{
  const { play, calls } = harness({ phase: 'rolling' })
  await play.playTrait(static1)
  ok('nothing plays mid-roll', [calls.added.length, calls.cascades.length], [0, 0])
}
{
  const { play, calls } = harness()
  await play.playTrait({ ...static1, enabled: false })
  ok('nothing plays from a disabled trait', [calls.added.length, calls.cascades.length], [0, 0])
}
{
  const { play, calls } = harness()
  await play.playTrait({ id: 'ts-e', name: 'empty', ratingType: 'STATIC', dice: [], polarity: 'POSITIVE' })
  ok('a die-less trait still cascades, then contributes nothing', [calls.cascades.length, calls.added.length], [1, 0])
}

// ── Resource: spend one, single-type only ──────────────────────────────────
{
  const { play, calls } = harness()
  await play.playTrait(resource1)
  ok('a single-type resource spends its die', calls.spends, [{ kind: 'resource', tsId: 'ts-3', die: 'd8' }])
  ok('…and the spent die joins the pool as a resource', calls.added, [
    { die: 'd8', source: 'fuel', label: 'FUEL', tsId: 'ts-3', negative: false, resource: true, armedSfxIds: ['sfx-x'] },
  ])
  ok('…and is remembered for refund', calls.remembered, [{ id: 'ts-3', die: 'd8', kind: 'resource' }])
  ok('…and the entity is refreshed', calls.refreshes, ['resource-spend'])
}
{
  const { play, calls } = harness()
  await play.playTrait(resourceMixed)
  ok('a MIXED resource row click does nothing (its groups own that)', [calls.spends.length, calls.added.length], [0, 0])
}

// ── Challenge: polarity routes the die ────────────────────────────────────
{
  const { play, calls } = harness()
  await play.playTrait(doom)
  ok('a doom pool spends to the opposition', calls.spends, [{ kind: 'challenge', tsId: 'ts-5', die: 'd8', dest: 'opposition' }])
  ok('…and a die in the opposition pool is NOT refundable from a sheet', calls.remembered, [])
  ok('…and it joins the pool as a plain negative die', calls.added, [
    { die: 'd6', source: 'doom', label: 'DOOM', tsId: 'ts-5', negative: true, resource: false, armedSfxIds: ['sfx-x'] },
  ])
  ok('…and the trait\'s own dice follow the server', doom.dice, ['D6'])
  ok('…and the entity is refreshed', calls.refreshes, ['challenge-spend'])
}
{
  const { play, calls } = harness()
  await play.playTrait(progress)
  ok('a progress pool spends into its own pool', calls.spends, [{ kind: 'challenge', tsId: 'ts-6', die: 'd6', dest: 'pool' }])
  ok('…and it IS refundable', calls.remembered, [{ id: 'ts-6', die: 'd6', kind: 'challenge' }])
  ok('…and joins positive and resource-flagged', calls.added, [
    { die: 'd6', source: 'progress', label: 'PROGRESS', tsId: 'ts-6', negative: false, resource: true, armedSfxIds: ['sfx-x'] },
  ])
}
{
  const { play, calls } = harness({ challengeRes: null })
  await play.playTrait(doom)
  ok('a refused challenge spend adds nothing', calls.added, [])
}

// ── The affordance gate is the play gate plus a die ───────────────────────
{
  const { play } = harness()
  ok('canPlay allows a plain playable trait', play.canPlay(static1), true)
}
{
  const { play } = harness({ phase: 'rolling' })
  ok('canPlay refuses mid-roll', play.canPlay(static1), false)
  ok('canPlay refuses a disabled trait', play.canPlay({ ...static1, enabled: false }), false)
}

// ── The wire shape, straight from the server ──────────────────────────────
// `GET /locations/{id}/traits` sends snake_case keys and LOWERCASE enums; the play
// compares UPPERCASE on camelCase. BOTH halves of that mismatch shipped as bugs — a
// challenge trait played like a static one, pushing its raw dice at the roller
// instead of spending a die. So take literal wire entries through the normaliser.
{
  const { play, calls } = harness()
  await play.playTrait(normalizeLocationTrait({ id: 'ts-w1', name: 'population', rating_type: 'static', polarity: 'positive', dice: ['d6'] }))
  ok('a wire-shaped static trait contributes its die', calls.added.map(p => p.die), ['d6'])
}
{
  const { play, calls } = harness()
  await play.playTrait(normalizeLocationTrait({ id: 'ts-w2', name: 'doom', rating_type: 'challenge', polarity: 'negative', dice: ['d8'] }))
  ok('a wire-shaped challenge trait SPENDS a die', calls.spends, [{ kind: 'challenge', tsId: 'ts-w2', die: 'd8', dest: 'opposition' }])
  ok('…and only the spent die reaches the pool', calls.added.length, 1)
  ok('…as a negative die', calls.added[0].negative, true)
}
{
  // And the bug itself, kept as a case so the normaliser cannot be dropped: an
  // un-normalised wire entry reads as a static trait and pushes both dice.
  const { play, calls } = harness()
  await play.playTrait({ id: 'ts-w3', name: 'doom', rating_type: 'challenge', polarity: 'negative', dice: ['d8', 'd8'] })
  ok('pre-normalisation a challenge trait spent nothing', calls.spends.length, 0)
  ok('…and pushed its raw dice instead (the bug)', calls.added.map(p => p.dice), [['d8', 'd8']])
}

console.log(fail ? `\n  ${fail} failed\n` : '\n  all clear\n')
process.exit(fail ? 1 : 0)
