import { ref, onMounted } from 'vue'

const API_BASE = '/api/v1'

export function useApi() {
  const loading = ref(false)
  const error = ref(null)

  async function graphql(query, variables = {}) {
    loading.value = true
    error.value = null
    try {
      const r = await fetch(`${API_BASE}/graphql`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, variables })
      })
      const data = await r.json()
      if (data.errors) throw new Error(data.errors[0].message)
      return data.data
    } catch (e) {
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

  return { loading, error, graphql, roll, triggerSfx, spendResourceDie, recoverResourceDie }
}