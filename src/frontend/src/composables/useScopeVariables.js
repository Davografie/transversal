import { ref } from 'vue'
import { useApi } from './useApi.js'

// Available {variable} tokens for a trigger and/or menu context, sourced from
// the backend scopeVariables resolver.
export function useScopeVariables() {
  const { graphql } = useApi()
  const variables = ref([])

  async function fetchVariables(trigger = '', menuContext = '') {
    const data = await graphql(
      `query($trigger: String, $menuContext: String) { scopeVariables(trigger: $trigger, menuContext: $menuContext) }`,
      { trigger: trigger || '', menuContext: menuContext || '' }
    )
    variables.value = data?.scopeVariables || []
    return variables.value
  }

  return { variables, fetchVariables }
}
