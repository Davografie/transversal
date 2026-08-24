import { ref } from 'vue'
import { useApi } from './useApi.js'

// Available {variable} tokens for a trigger (auto-fire, manual, or menu),
// sourced from the backend scopeVariables resolver.
export function useScopeVariables() {
  const { graphql } = useApi()
  const variables = ref([])

  async function fetchVariables(trigger = '') {
    const data = await graphql(
      `query($trigger: String) { scopeVariables(trigger: $trigger) { name type } }`,
      { trigger: trigger || '' }
    )
    variables.value = data?.scopeVariables || []
    return variables.value
  }

  return { variables, fetchVariables }
}
