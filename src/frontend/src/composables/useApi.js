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

  async function roll(entityId, universe, dice, opposition = null) {
    loading.value = true
    error.value = null
    try {
      const r = await fetch(`${API_BASE}/roll`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entity_id: entityId, universe, dice, opposition })
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

  // ── Scene state (in-memory server persistence) ──
  async function savePool(locationId, playerId, dice) {
    if (!locationId || !playerId) return null
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/players/${playerId}/pool`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dice })
      })
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] savePool', e.message); return null }
  }

  async function getPool(locationId, playerId) {
    if (!locationId || !playerId) return null
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/players/${playerId}/pool`)
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] getPool', e.message); return null }
  }

  async function clearPool(locationId, playerId) {
    if (!locationId || !playerId) return null
    try {
      const r = await fetch(`${API_BASE}/locations/${locationId}/players/${playerId}/pool`, { method: 'DELETE' })
      if (!r.ok) throw new Error(await r.text())
      return await r.json()
    } catch (e) { console.error('[API] clearPool', e.message); return null }
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

  return { loading, error, graphql, roll, triggerSfx, spendResourceDie, recoverResourceDie, imagenEntity, animateEntity, savePool, getPool, clearPool, setDifficulty, getDifficulty }
}