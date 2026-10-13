import { ref } from 'vue'
import { useApi } from './useApi.js'

// The instances of one trait definition, and the bulk edits over them.
//
// **Not** module-scope state: two of these panels can be open at once (one per
// trait — the panel is opened as a child of a trait editor), and they are about
// different definitions, so sharing a list would show one trait's instances under
// another's title.
//
// The read is the API's `traitInstances(traitId)`, the inverse of every other
// trait-setting read: instances are otherwise only reachable *from* a host.
// `host` is resolved by the server because only it can answer the four kinds —
// see `utils/traitInstanceHost.js` for how the client reads what comes back.

const QUERY = `query($id: ID!) {
  traitInstances(traitId: $id) {
    id traitId entityId fromType projectionId parentTraitsettingId
    ratingType dice spentDice capacity polarity statement notes order tags sfxIds enabled
    host {
      kind entityId entityName entityType universe
      aboutId aboutName aboutType relationshipType
      parentTraitsettingId parentTraitId parentTraitName
    }
  }
}`

// One definition can carry **hundreds** of instances — `essence` carries 547
// today — and a bulk edit is one mutation per instance. Firing all of them at
// once (what the trait-definition batch editor does, over a much smaller set)
// would put 500 concurrent writes on the API, so the fan-out is bounded.
const CONCURRENCY = 6

export function useTraitInstances() {
  const { graphql } = useApi()

  const instances = ref([])
  const loading = ref(false)
  const error = ref('')
  // Set after a bulk run: how many of the selection actually took.
  const lastRun = ref(null)

  async function fetchInstances(traitId) {
    if (!traitId) return
    loading.value = true
    error.value = ''
    try {
      const data = await graphql(QUERY, { id: traitId })
      instances.value = data?.traitInstances || []
    } catch (e) {
      error.value = 'Could not load instances: ' + (e?.message || e)
      instances.value = []
    } finally {
      loading.value = false
    }
  }

  /** Run `work` for each id, at most `CONCURRENCY` at a time. */
  async function runBounded(ids, work) {
    const succeeded = []
    const failed = []
    let next = 0
    const worker = async () => {
      while (next < ids.length) {
        const id = ids[next++]
        try {
          await work(id)
          succeeded.push(id)
        } catch {
          failed.push(id)
        }
      }
    }
    await Promise.all(
      Array.from({ length: Math.min(CONCURRENCY, ids.length) }, () => worker()),
    )
    return { succeeded, failed }
  }

  /**
   * Apply a partial change to many instances — the same shape the trait-set batch
   * editor uses, one `updateTraitSetting` per id. Only the keys present are
   * written (the resolver tests each for `null`), so `{ dice: [] }` clears dice
   * while omitting `dice` leaves them alone.
   */
  async function updateInstances(ids, changes) {
    if (!ids.length) return { succeeded: [], failed: [] }
    const input = { ...changes }
    const result = await runBounded(ids, (id) =>
      graphql(
        `mutation($id: ID!, $input: TraitSettingUpdateInput!) { updateTraitSetting(id: $id, input: $input) { id } }`,
        { id, input },
      ),
    )
    lastRun.value = { kind: 'update', ...result }
    return result
  }

  /** Remove instances outright — the migration's duplicates and dead weight. */
  async function removeInstances(ids) {
    if (!ids.length) return { succeeded: [], failed: [] }
    const result = await runBounded(ids, (id) =>
      graphql(`mutation($id: ID!) { removeTraitSetting(id: $id) }`, { id }),
    )
    lastRun.value = { kind: 'remove', ...result }
    return result
  }

  return { instances, loading, error, lastRun, fetchInstances, updateInstances, removeInstances }
}
