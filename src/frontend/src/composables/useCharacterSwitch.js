import { ref } from 'vue'
import { RESONANCE, signatureOf } from './resonance.js'

/**
 * Switching which character you play — the razmerit "harmonising" animation and
 * the work behind it (claim, control, list refresh, location re-init).
 *
 * `locationInit` hands back the app's location bootstrap promise so the switch
 * can await the new scene. The ordering matters: reset() must be called *before*
 * `entityId` is assigned, because the app's `flush: 'sync'` watcher on entityId
 * re-arms that promise during the assignment.
 */
export function useCharacterSwitch({
  entityId,
  playerId,
  showLoginOverlay,
  fetchPlayerEntities,
  locationInit,
}) {
  const charPending = ref(null)
  const charSwitchLoading = ref(false)
  const charSwitchDone = ref(false)
  const resonanceFrom = ref([])
  const resonanceTo = ref([])
  let charSwitchToken = 0
  let charSwitchPreviousEntityId = null

  async function fetchCharacterSignature(id) {
    if (!id) return []
    try {
      const r = await fetch('/api/v1/graphql', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: `query($id: ID!) { character(id: $id) { entity { id razmerit effectiveTraitSettings { id traitId traitsetId dice polarity fromType projectionId } } } }`,
          variables: { id }
        })
      })
      const json = await r.json()
      const c = json.data?.character
      if (!c) return []
      return signatureOf(c.entity?.effectiveTraitSettings || [], c.entity?.razmerit || 0, RESONANCE.egoBoost)
    } catch {
      return []
    }
  }

  function beginCharacterSwitch(e) {
    if (!e?.id || charSwitchLoading.value) return
    const token = ++charSwitchToken
    charPending.value = e
    charSwitchLoading.value = true
    charSwitchDone.value = false
    charSwitchPreviousEntityId = entityId.value

    const aId = entityId.value
    const bId = e.id
    resonanceFrom.value = []
    resonanceTo.value = []
    const sigAP = fetchCharacterSignature(aId).then(s => { if (token === charSwitchToken) resonanceFrom.value = s })
    const sigBP = fetchCharacterSignature(bId).then(s => { if (token === charSwitchToken) resonanceTo.value = s })

    // Commit the perspective and load everything in the background.
    locationInit.reset()
    entityId.value = bId
    const claimP = playerId.value
      ? fetch(`/api/v1/players/${playerId.value}/claim/${bId}`, { method: 'POST' }).catch(() => {})
      : Promise.resolve()
    const controlP = playerId.value
      ? fetch(`/api/v1/players/${playerId.value}/control/${bId}`, { method: 'POST' }).catch(() => {})
      : Promise.resolve()
    const entitiesP = fetchPlayerEntities()
    const locationP = locationInit.current() || Promise.resolve()
    const minDelayP = new Promise(resolve => setTimeout(resolve, RESONANCE.durationMs))

    Promise.all([claimP, controlP, entitiesP, locationP, minDelayP, sigAP, sigBP]).then(() => {
      if (token !== charSwitchToken) return
      charSwitchDone.value = true
      // Let the final fan-out read for a beat before closing.
      setTimeout(() => {
        if (token !== charSwitchToken) return
        charSwitchLoading.value = false
        charPending.value = null
        charSwitchPreviousEntityId = null
        resonanceFrom.value = []
        resonanceTo.value = []
        showLoginOverlay.value = false
      }, RESONANCE.fanMs)
    })
  }

  function cancelCharacterSwitch() {
    charSwitchToken++
    if (charSwitchPreviousEntityId != null && entityId.value !== charSwitchPreviousEntityId) {
      entityId.value = charSwitchPreviousEntityId
    }
    charSwitchPreviousEntityId = null
    charSwitchLoading.value = false
    charSwitchDone.value = false
    charPending.value = null
    resonanceFrom.value = []
    resonanceTo.value = []
  }

  /** Drop any in-flight switch animation (the overlay was opened or closed). */
  function resetSwitchAnimation() {
    charSwitchLoading.value = false
    charSwitchDone.value = false
    charSwitchToken++
    charPending.value = null
    charSwitchPreviousEntityId = null
    resonanceFrom.value = []
    resonanceTo.value = []
  }

  return {
    charPending, charSwitchLoading, charSwitchDone, resonanceFrom, resonanceTo,
    beginCharacterSwitch, cancelCharacterSwitch, resetSwitchAnimation,
  }
}
