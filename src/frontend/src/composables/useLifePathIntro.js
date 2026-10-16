import { ref } from 'vue'

/**
 * Life paths a rule has shown to a player, waiting to be looked at ([[B303]]).
 *
 * The effect is `client/life_path`, and the server says only *which path* and
 * *whose screen*. The **surface is decided here**, because this is the only side
 * that knows how the character came to exist: a character the player created in
 * the settings overlay is shown there, and one that arrived another way (a rule
 * made it, say) is shown in that character's sheet. See
 * `services/client_actions.py` — the payload deliberately has no surface field.
 *
 * Kept per character and **persisted**, because it is an onboarding moment: a
 * reload between "your character exists" and "here is its life path" should not
 * lose it. Dismissing is the player saying they have seen it.
 */

const STORAGE_KEY = 'sfx.lifePathIntros'

function _load() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : null
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

// One module-level map, so every caller sees the same pending set.
const intros = ref(_load())

function _persist() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(intros.value))
  } catch {
    /* private mode, quota — the intro still works for this session */
  }
}

export function useLifePathIntro() {
  /**
   * Record that `lifePathId` should be shown to `characterId`.
   *
   * `surface` is `'overlay'` or `'sheet'`. Re-showing the same path on the same
   * character is idempotent rather than duplicated.
   */
  function introduce(characterId, lifePathId, surface = 'overlay') {
    if (!characterId || !lifePathId) return
    intros.value = { ...intros.value, [characterId]: { lifePathId, surface } }
    _persist()
  }

  /** The pending intro for a character, optionally only on one surface. */
  function introFor(characterId, surface = '') {
    const entry = intros.value[characterId]
    if (!entry) return null
    if (surface && entry.surface !== surface) return null
    return entry
  }

  /**
   * The first pending intro on a surface — what the settings overlay renders.
   *
   * The overlay is one panel, so it can carry one at a time; the newest wins
   * because `introduce` replaces rather than appends.
   */
  function firstFor(surface) {
    const hit = Object.entries(intros.value).find(([, e]) => e && e.surface === surface)
    return hit ? { characterId: hit[0], lifePathId: hit[1].lifePathId } : null
  }

  /** The player has seen it — stop showing it. */
  function dismiss(characterId) {
    if (!(characterId in intros.value)) return
    const next = { ...intros.value }
    delete next[characterId]
    intros.value = next
    _persist()
  }

  return { intros, introduce, introFor, firstFor, dismiss }
}
