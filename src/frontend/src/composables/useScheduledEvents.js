import { useApi } from './useApi.js'

// Timer `event` values are game-boundary signals, not wall-clock units, so the
// display speaks in countdowns ("2 scenes"), never timestamps.
const EVENT_LABELS = {
  beat: 'beat',
  scene: 'scene',
  session: 'session',
  rolls: 'roll',
  location_changed: 'location change',
}

function eventLabel(event) {
  return EVENT_LABELS[event] || event
}

/**
 * Render one or more timers as a human countdown phrase.
 * A single timer → "2 scenes". Multiple timers are joined by the combine mode
 * ("or" for first-to-fire, "and" for all-transpired).
 */
export function formatTimers(timers = [], combine = 'FIRST_TO_FIRE') {
  if (!timers || !timers.length) return ''
  const parts = timers.map((t) => {
    const label = eventLabel(t.event)
    const unit = t.remaining === 1 ? label : `${label}s`
    return `${t.remaining} ${unit}`
  })
  if (parts.length === 1) return parts[0]
  const sep = combine === 'ALL_TRANSPIRED' ? ' and ' : ' or '
  return parts.join(sep)
}

/**
 * Access the centrally-scheduled timer store.
 *
 * ``targetType`` is ``"entity"`` or ``"trait_setting"``; ``targetId`` scopes to
 * one owner (omit/null for every event of that type). The raw ``ScheduledEvent``
 * is returned with its ``targetType``/``targetId`` so callers can reconnect a
 * timer to its owner in the UI.
 */
export function useScheduledEvents() {
  const { graphql } = useApi()

  async function fetchFor(targetType, targetId = null, targetIds = null) {
    const data = await graphql(
      `query($targetType: String, $targetId: ID, $targetIds: [ID!]) {
        scheduledEvents(targetType: $targetType, targetId: $targetId, targetIds: $targetIds) {
          id
          targetType
          targetId
          sourceSfxId
          combine
          timers { event remaining }
          effect { type action target result }
        }
      }`,
      { targetType, targetId: targetId || null, targetIds: targetIds || null },
    )
    return data?.scheduledEvents || []
  }

  return { fetchFor, formatTimers, eventLabel }
}
