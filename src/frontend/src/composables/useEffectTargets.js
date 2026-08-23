import { ref } from 'vue'
import { useApi } from '@/composables/useApi.js'

// Fetch selectable candidates for a choose/random effect target, resolved by
// the shared backend resolver (same candidate set the `random` target mode uses).
export function useEffectTargets() {
  const { graphql } = useApi()
  const loading = ref(false)
  const candidates = ref([])

  async function fetchTargets(kind, scope, entityId, action, filter) {
    if (!kind) {
      candidates.value = []
      return []
    }
    loading.value = true
    try {
      const data = await graphql(
        `query($kind: String!, $entityId: ID, $scope: String, $action: String, $filter: JSON) {
          targetCandidates(kind: $kind, entityId: $entityId, scope: $scope, action: $action, filter: $filter) {
            id name universe
          }
        }`,
        { kind, entityId: entityId || null, scope: scope || null, action: action || null, filter: filter || null }
      )
      candidates.value = data?.targetCandidates || []
      return candidates.value
    } finally {
      loading.value = false
    }
  }

  return { loading, candidates, fetchTargets }
}
