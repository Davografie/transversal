import { ref, watch } from 'vue'
import { useApi } from './useApi.js'
import { useMediaQuality } from './useMediaQuality.js'

/**
 * Resolve an entity's media URL by role tag.
 *
 * Roles are exactly: 'background', 'sheet', 'navdot' — backed by the
 * entity's `image(role)` GraphQL field, which reads the role tags from
 * `entity_images` and never falls back to the legacy denormalized
 * `background_image` field.
 *
 * `entityId` may be a ref, a computed, or a plain string. The resolved URL
 * is passed through the quality preference (low-quality swaps to `_Small`,
 * cache-aware so an already-cached original wins).
 */
export function useEntityMedia(entityId, role) {
  const { graphql } = useApi()
  const { resolveMediaUrl } = useMediaQuality()

  const src = ref('')
  const loading = ref(false)

  async function load() {
    const id = typeof entityId === 'object' && entityId && 'value' in entityId
      ? entityId.value
      : entityId
    if (!id || !role) {
      src.value = ''
      return
    }
    loading.value = true
    try {
      const data = await graphql(
        `query($id: ID!, $role: String!) { entity(id: $id) { image(role: $role) } }`,
        { id, role }
      )
      const raw = data?.entity?.image || ''
      src.value = await resolveMediaUrl(raw)
    } catch {
      src.value = ''
    } finally {
      loading.value = false
    }
  }

  const idSource = () =>
    typeof entityId === 'object' && entityId && 'value' in entityId
      ? entityId.value
      : entityId

  watch(idSource, load, { immediate: true })

  return { src, loading, load }
}
