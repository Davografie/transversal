import { ref, onMounted } from 'vue'

const API_BASE = '/api/v1'

export function useApi() {
  const loading = ref(false)
  const error = ref(null)

  async function graphql(query, variables = {}) {
    loading.value = true
    error.value = null
    try {
      const payload = JSON.stringify({ query, variables })
      console.log('[API] graphql', query.substring(0, 80), JSON.stringify(variables))
      const r = await fetch(`${API_BASE}/graphql`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload
      })
      const data = await r.json()
      console.log('[API] graphql response', JSON.stringify({ ok: r.ok, hasData: !!data.data, hasErrors: !!data.errors }))
      if (data.errors) { console.error('[API] graphql errors', JSON.stringify(data.errors)); throw new Error(data.errors[0].message) }
      return data.data
    } catch (e) {
      console.error('[API] graphql exception', e.message)
      error.value = e.message
      return null
    } finally {
      loading.value = false
    }
  }

  async function _rollEndpoint(path, body) {
    loading.value = true
    error.value = null
    try {
      const r = await fetch(`${API_BASE}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) {
      error.value = e.message
      return null
    } finally {
      loading.value = false
    }
  }

  async function cortexRoll(locationId, entityId) {
    return _rollEndpoint(`/locations/${locationId}/pools/${entityId}/cortex-roll`, {})
  }

  async function simplifiedRoll(locationId, entityId) {
    return _rollEndpoint(`/locations/${locationId}/pools/${entityId}/simplified-roll`, {})
  }

  async function difficultyRoll(locationId, entityId) {
    return _rollEndpoint(`/locations/${locationId}/pools/${entityId}/difficulty-roll`, {})
  }

  async function selectDice(locationId, entityId, totalIndices, effectIndex) {
    return _rollEndpoint(`/locations/${locationId}/pools/${entityId}/select`, {
      total_indices: totalIndices,
      effect_index: effectIndex,
    })
  }

  async function resolvePool(locationId, entityId) {
    return _rollEndpoint(`/locations/${locationId}/pools/${entityId}/resolve`, {})
  }

  async function markHitchesBought(locationId, entityId, indices) {
    return _rollEndpoint(`/locations/${locationId}/pools/${entityId}/hitches/mark-bought`, { indices })
  }

  async function triggerSfx(entityId, sfxName, universe = 'earth', context = {}) {
    loading.value = true
    error.value = null
    try {
      const r = await fetch(`${API_BASE}/effects/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entity_id: entityId, sfx_name: sfxName, universe, trigger: 'manual', context })
      })
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) {
      error.value = e.message
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * Take back a manual activation that has not committed yet: the undos it still
   * owes are applied, its deferred parts are dropped, and what was still waiting
   * on a roll is un-armed. Rolling the dice (or a delayed part firing) commits
   * the rule, and after that there is nothing left to end.
   */
  async function endSfx(entityId, sfxId) {
    error.value = null
    try {
      const r = await fetch(`${API_BASE}/effects/end`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entity_id: entityId, sfx_id: sfxId })
      })
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) {
      error.value = e.message
      return null
    }
  }

  async function spendResourceDie(tsId, die, count = 1) {
    error.value = null
    try {
      const r = await fetch(`${API_BASE}/resource-pool/${tsId}/spend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ die, count })
      })
      if (!r.ok) {
        const msg = await r.text()
        throw new Error(msg)
      }
      return await r.json()
    } catch (e) {
      error.value = e.message
      return null
    }
  }

  async function recoverResourceDie(tsId, die, count = 1) {
    error.value = null
    try {
      const r = await fetch(`${API_BASE}/resource-pool/${tsId}/recover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ die, count })
      })
      if (!r.ok) {
        const msg = await r.text()
        throw new Error(msg)
      }
      return await r.json()
    } catch (e) {
      error.value = e.message
      return null
    }
  }

  async function spendChallengeDie(tsId, die, destination = 'opposition') {
    error.value = null
    try {
      const r = await fetch(`${API_BASE}/challenge-pool/${tsId}/spend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ die, destination })
      })
      if (!r.ok) {
        const msg = await r.text()
        throw new Error(msg)
      }
      return await r.json()
    } catch (e) {
      error.value = e.message
      return null
    }
  }

  async function imagenEntity(entityId, projectionId = '') {
    loading.value = true
    error.value = null
    try {
      const r = await fetch(`${API_BASE}/imagen/${entityId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ projection_id: projectionId }),
      })
      if (!r.ok) {
        const msg = await r.text()
        throw new Error(msg)
      }
      return await r.json()
    } catch (e) {
      error.value = e.message
      return null
    } finally {
      loading.value = false
    }
  }

  async function animateEntity(entityId) {
    loading.value = true
    error.value = null
    try {
      const r = await fetch(`${API_BASE}/animate/${entityId}`, { method: 'POST' })
      if (!r.ok) {
        const msg = await r.text()
        throw new Error(msg)
      }
      return await r.json()
    } catch (e) {
      error.value = e.message
      return null
    } finally {
      loading.value = false
    }
  }

  // ── Scene state (in-memory server persistence, keyed by entity) ──
  async function savePool(locationId, entityId, dice) {
    if (!locationId || !entityId) return null
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/pools/${entityId}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dice })
      })
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] savePool', e.message); return null }
  }

  async function offerNegative(locationId, entityId, opponentId, traitSettingId, dice, label = '') {
    if (!locationId || !entityId || !opponentId) return null
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/pools/${entityId}/offer-negative`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ opponent_id: opponentId, trait_setting_id: traitSettingId, dice, label })
      })
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] offerNegative', e.message); return null }
  }

  async function getPool(locationId, entityId) {
    if (!locationId || !entityId) return null
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/pools/${entityId}`)
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] getPool', e.message); return null }
  }

  async function clearPool(locationId, entityId) {
    if (!locationId || !entityId) return null
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/pools/${entityId}`, { method: 'DELETE' })
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] clearPool', e.message); return null }
  }

  async function listPools(locationId) {
    if (!locationId) return null
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/pools`)
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] listPools', e.message); return null }
  }

  async function listAllPools() {
    try {
      const r = await fetch(`${API_BASE}/pools`)
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] listAllPools', e.message); return null }
  }

  async function getActivity() {
    try {
      const r = await fetch(`${API_BASE}/activity`)
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] getActivity', e.message); return null }
  }

  // ── Contest actions ──
  async function setOpposition(locationId, entityId, opponentId, universe = 'earth') {
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/pools/${entityId}/set-opposition`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ opponent_id: opponentId, universe })
      })
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] setOpposition', e.message); return null }
  }

  async function setResult(locationId, entityId, committed) {
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/pools/${entityId}/set`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(committed)
      })
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] setResult', e.message); return null }
  }

  async function setStakes(locationId, entityId, highStakes) {
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/pools/${entityId}/stakes`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ high_stakes: highStakes })
      })
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] setStakes', e.message); return null }
  }

  async function giveIn(locationId, entityId) {
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/pools/${entityId}/give-in`, { method: 'POST' })
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] giveIn', e.message); return null }
  }

  async function preventTakenOut(locationId, entityId, effectDie = null) {
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/pools/${entityId}/prevent-taken-out`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ effect_die: effectDie }),
      })
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] preventTakenOut', e.message); return null }
  }

  async function push(locationId, entityId) {
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/pools/${entityId}/push`, { method: 'POST' })
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] push', e.message); return null }
  }

  async function getTargetingBans(entityId) {
    if (!entityId) return { bans: [] }
    try {
      const r = await fetch(`${API_BASE}/entities/${entityId}/targeting-bans`)
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] getTargetingBans', e.message); return { bans: [] } }
  }

  async function getContest(locationId, entityId) {
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/pools/${entityId}/contest`)
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] getContest', e.message); return null }
  }

  async function clearContest(locationId, entityId) {
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/pools/${entityId}/clear`, { method: 'POST' })
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] clearContest', e.message); return null }
  }

  async function setDifficulty(locationId, difficulty) {
    if (!locationId) return null
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/difficulty`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ difficulty })
      })
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] setDifficulty', e.message); return null }
  }

  async function getDifficulty(locationId) {
    if (!locationId) return null
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/difficulty`)
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] getDifficulty', e.message); return null }
  }

  async function nextBeat(locationId) {
    if (!locationId) return null
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/next-beat`, { method: 'POST' })
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] nextBeat', e.message); return null }
  }

  async function advanceScene() {
    try {
      const r = await fetch(`${API_BASE}/scenes/advance`, { method: 'POST' })
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] advanceScene', e.message); return null }
  }

  return { loading, error, graphql, cortexRoll, simplifiedRoll, difficultyRoll, selectDice, resolvePool, markHitchesBought, triggerSfx, endSfx, spendResourceDie, recoverResourceDie, spendChallengeDie, imagenEntity, animateEntity, savePool, offerNegative, getPool, clearPool, listPools, listAllPools, getActivity, setOpposition, setResult, setStakes, giveIn, preventTakenOut, push, getTargetingBans, getContest, clearContest, setDifficulty, getDifficulty, nextBeat, advanceScene }
}