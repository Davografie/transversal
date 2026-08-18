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
      console.log('[API] graphql', query.substring(0, 80), variables)
      const r = await fetch(`${API_BASE}/graphql`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload
      })
      const data = await r.json()
      console.log('[API] graphql response', { ok: r.ok, hasData: !!data.data, hasErrors: !!data.errors })
      if (data.errors) { console.error('[API] graphql errors', data.errors); throw new Error(data.errors[0].message) }
      return data.data
    } catch (e) {
      console.error('[API] graphql exception', e.message)
      error.value = e.message
      return null
    } finally {
      loading.value = false
    }
  }

  async function roll(entityId, universe, dice, opposition = null, pipeline = null, hitchesApply = true) {
    loading.value = true
    error.value = null
    try {
      const body = { entity_id: entityId, universe, dice, opposition, hitches_apply: hitchesApply }
      if (pipeline) body.pipeline = pipeline
      const r = await fetch(`${API_BASE}/roll`, {
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

  async function imagenEntity(entityId) {
    loading.value = true
    error.value = null
    try {
      const r = await fetch(`${API_BASE}/imagen/${entityId}`, { method: 'POST' })
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

  async function resolveContest(locationId, entityId) {
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/pools/${entityId}/resolve`, { method: 'POST' })
      if (r.status === 409) return { error: 'Both sides must have dice assembled' }
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] resolveContest', e.message); return null }
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

  return { loading, error, graphql, roll, triggerSfx, spendResourceDie, recoverResourceDie, imagenEntity, animateEntity, savePool, getPool, clearPool, listPools, setOpposition, resolveContest, clearContest, setDifficulty, getDifficulty, nextBeat }
}