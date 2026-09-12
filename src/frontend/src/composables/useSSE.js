import { ref, watch, onUnmounted, isRef } from 'vue'

export function useSSE(sessionId, entityId, playerId) {
  const connected = ref(false)
  const lastEvent = ref(null)
  const error = ref(null)
  let source = null

  function connect() {
    disconnect()
    const sid = isRef(sessionId) ? sessionId.value : sessionId
    const eid = isRef(entityId) ? entityId.value : entityId
    const pid = isRef(playerId) ? playerId.value : playerId
    console.log('[SSE] connect() called — sid:', sid, 'eid:', eid, 'isDefault:', sid === 'session-default')
    if (!sid || !eid || sid === 'session-default') {
      console.log('[SSE] connect() skipped — guard blocked (session-default or missing id)')
      return
    }

    const url = `/api/v1/stream?session_id=${sid}&entity_id=${eid}&player_id=${pid || ''}`
    console.log('[SSE] creating EventSource →', url)
    source = new EventSource(url)

    source.onopen = () => {
      console.log('[SSE] onopen — connected!')
      connected.value = true
      error.value = null
    }
    source.onerror = (e) => {
      console.log('[SSE] onerror — connection failed. readyState:', source?.readyState)
      connected.value = false
      error.value = 'SSE connection failed'
    }

    const eventTypes = [
      'location_changed', 'trait_updated', 'razmerit_changed',
      'roll_result', 'pool_updated', 'sfx_triggered', 'sfx_ended', 'beat_end', 'scene_change',
      'entity_updated', 'entity_moved', 'difficulty_set', 'sfx_choice_required',
      'contest_challenged', 'contest_set', 'contest_resolved', 'contest_give_in', 'contest_compare', 'contest_push', 'contest_stakes', 'traits_revealed',
      'dice_limits_changed',
      'main_active', 'presence_changed',
      'session_started', 'session_ended'
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
  if (isRef(playerId)) watch(() => playerId.value, connect)

  onUnmounted(disconnect)

  return { connected, lastEvent, error }
}
