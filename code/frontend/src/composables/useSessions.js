import { ref } from 'vue'

const API_BASE = '/api/v1'

export function useSessions() {
  const sessions = ref([])
  const currentSession = ref(null)
  const loading = ref(false)
  const error = ref(null)

  async function listSessions() {
    loading.value = true
    try {
      const r = await fetch(`${API_BASE}/sessions`)
      sessions.value = await r.json()
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function createSession(name = 'New Session', universe = 'earth') {
    loading.value = true
    try {
      const r = await fetch(`${API_BASE}/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, universe })
      })
      const s = await r.json()
      sessions.value.push(s)
      return s
    } catch (e) {
      error.value = e.message
      return null
    } finally {
      loading.value = false
    }
  }

  async function joinSession(sessionId, entityId, playerId = '') {
    loading.value = true
    try {
      const r = await fetch(`${API_BASE}/sessions/${sessionId}/join`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entity_id: entityId, player_id: playerId })
      })
      currentSession.value = await r.json()
      return currentSession.value
    } catch (e) {
      error.value = e.message
      return null
    } finally {
      loading.value = false
    }
  }

  async function publishEvent(sessionId, eventType, data) {
    await fetch(`${API_BASE}/sessions/${sessionId}/publish`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event: eventType, data })
    })
  }

  async function leaveSession(sessionId, entityId) {
    await fetch(`${API_BASE}/sessions/${sessionId}/leave`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entity_id: entityId })
    })
    currentSession.value = null
  }

  return { sessions, currentSession, loading, error, listSessions, createSession, joinSession, leaveSession, publishEvent }
}
