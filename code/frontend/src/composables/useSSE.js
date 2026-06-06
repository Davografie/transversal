import { ref, watch, onUnmounted, isRef } from 'vue'

export function useSSE(sessionId, entityId) {
  const connected = ref(false)
  const lastEvent = ref(null)
  const error = ref(null)
  let source = null

  function connect() {
    disconnect()
    const sid = isRef(sessionId) ? sessionId.value : sessionId
    const eid = isRef(entityId) ? entityId.value : entityId
    if (!sid || !eid || sid === 'session-default') return

    const url = `/api/v1/stream?session_id=${sid}&entity_id=${eid}`
    source = new EventSource(url)

    source.onopen = () => {
      connected.value = true
      error.value = null
    }
    source.onerror = (e) => {
      connected.value = false
      error.value = 'SSE connection failed'
    }

    const eventTypes = [
      'location_changed', 'trait_updated', 'razmerit_changed',
      'roll_result', 'pool_updated', 'sfx_triggered', 'beat_end', 'scene_change',
      'entity_updated', 'entity_moved'
    ]

    for (const type of eventTypes) {
      source.addEventListener(type, (e) => {
        try {
          const data = JSON.parse(e.data)
          lastEvent.value = { type, data, time: Date.now() }
        } catch {}
      })
    }
  }

  function disconnect() {
    if (source) {
      source.close()
      source = null
    }
    connected.value = false
  }

  // Watch for ref changes and reconnect (handles initial + subsequent)
  if (isRef(entityId)) watch(() => entityId.value, connect, { immediate: true })
  if (isRef(sessionId)) watch(() => sessionId.value, connect, { immediate: true })

  onUnmounted(disconnect)

  return { connected, lastEvent, error }
}
