import { useApi } from './useApi.js'
import { useTraitsConfig } from './useTraitsConfig.js'

// ── A member's role in a faction ─────────────────────
// The role is not a field on the entity or the faction: it is a
// **relationship-anchored trait setting** on the membership tie, whose statement
// holds the role text ("sect elder") and whose rating holds the rank. The tie can
// be written from either end — a faction's roster, or an entity's faction list —
// so the resolution lives here once instead of in both panels.
//
// Two facts from the API shape this:
//   • A relationship-anchored setting comes back carrying its **contact**
//     (`relationshipContactId`), so a tie is identified without its edge key.
//   • A second `addRelationshipTrait` for the same tie is refused (the setting id
//     is deterministic, `{edge}:{trait}`), so an existing role is *updated*.
const RELATIONS_SET = 'relations'
const ROLE_TRAIT = 'role'

export function useFactionRoles() {
  const { graphql, error: apiError } = useApi()
  const { traitsets, fetchTraitsConfig } = useTraitsConfig()

  // The role trait is the one named `role` inside the traitset named `relations`
  // — the rule the MCP tools resolve by, and deliberately by name: the registry
  // holds two traits called `role` and the authored rosters use this one.
  async function roleTraitId() {
    if (!traitsets.value.length) await fetchTraitsConfig()
    const relations = (traitsets.value || []).find(ts => ts.name === RELATIONS_SET)
    return (relations?.traits || []).find(t => t.name === ROLE_TRAIT)?.id || ''
  }

  function _settingsQuery(entityId) {
    return graphql(
      `query($id: ID!) { entity(id: $id) { traitSettings { id traitId fromType relationshipType relationshipContactId } } }`,
      { id: entityId },
    )
  }

  // `{ [otherEndId]: settingId }` for this entity's membership ties — one read
  // that serves every row of a list.
  async function roleSettingsByContact(entityId) {
    const traitId = await roleTraitId()
    if (!traitId || !entityId) return {}
    const data = await _settingsQuery(entityId)
    const map = {}
    for (const ts of data?.entity?.traitSettings || []) {
      if (ts.fromType === 'relationship' && ts.relationshipType === 'membership' && ts.traitId === traitId) {
        map[ts.relationshipContactId] = ts.id
      }
    }
    return map
  }

  // Write `memberId`'s role in `factionId`. Pass a known `settingId` when the
  // caller already read the tie; otherwise it is looked up here.
  async function setRole({ memberId, factionId, statement, settingId = '' }) {
    if (!memberId || !factionId) return { ok: false, error: 'No tie to write.' }
    const traitId = await roleTraitId()
    if (!traitId) return { ok: false, error: 'Could not resolve the relations “role” trait.' }

    const next = (statement || '').trim()
    // Always resolve the tie when the caller did not hand one over — a clear has
    // to find the setting to remove it, exactly like a write has to find it to
    // update it.
    let id = settingId
    if (!id) id = (await roleSettingsByContact(memberId))[factionId] || ''

    let res = null
    let wrote = ''          // the setting the tie now has ('' once cleared)
    if (!next) {
      // Clearing removes the setting: the roster read falls back to the trait id
      // when a role setting has no statement, so a blank one would read as an id.
      if (!id) return { ok: true, settingId: '' }
      res = await graphql(`mutation($id: ID!) { removeTraitSetting(id: $id) }`, { id })
    } else if (id) {
      res = await graphql(
        `mutation($id: ID!, $input: TraitSettingUpdateInput!) { updateTraitSetting(id: $id, input: $input) { id statement } }`,
        { id, input: { statement: next } },
      )
      wrote = id
    } else {
      res = await graphql(
        `mutation($from: ID!, $to: ID!, $relType: String!, $traitId: ID!, $die: DieType!, $elevated: Boolean!, $statement: String!) {
          addRelationshipTrait(fromEntityId: $from, toEntityId: $to, relType: $relType, traitId: $traitId, die: $die, elevated: $elevated, statement: $statement) { id statement }
        }`,
        { from: memberId, to: factionId, relType: 'membership', traitId, die: 'D4', elevated: false, statement: next },
      )
    }
    // Read the reason here: every call clears the api error ref on the way in, so
    // it cannot be read after another request.
    if (!res) return { ok: false, error: apiError.value || 'Could not save the role.' }
    // The setting the tie now carries, so a caller can patch its row in place and
    // skip the lookup on the next edit of that row.
    return { ok: true, settingId: wrote || res?.addRelationshipTrait?.id || '' }
  }

  // Drop the member → faction tie. A `false` back from the mutation means there
  // was no membership edge to remove: the roster slot is a `relation` tie carrying
  // roster traits, which is not this gesture's to delete (it may carry non-roster
  // traits too).
  async function removeMembership({ memberId, factionId }) {
    if (!memberId || !factionId) return { ok: false, error: 'No tie to remove.' }
    const res = await graphql(
      `mutation($input: DeleteRelationshipInput!) { deleteRelationship(input: $input) }`,
      { input: { fromEntityId: memberId, toEntityId: factionId, type: 'membership' } },
    )
    if (!res) return { ok: false, error: apiError.value || 'Could not remove the membership.' }
    return { ok: true, nothingRemoved: res.deleteRelationship === false }
  }

  // The factions this entity is on the roster of — the inverse of the roster
  // read.
  //
  // ⚠ There is no GraphQL field for this yet (`repo.get_entity_factions` is
  // reachable only through `coMembers` and the `actor_faction:` target scope), so
  // it is assembled: `relatedEntities` gives every entity this one is tied to in
  // either direction, and each faction among them is then **confirmed against the
  // roster read** — which is the only read that can tell a roster slot from a
  // mere posture tie (a `relation` tie with no role/rank is not a slot, and an
  // edge's type is not exposed). That is one extra query per tied faction; a
  // `Entity.factions` field over the existing repo method would collapse it to one
  // query for the whole list.
  async function factionsFor(entityId) {
    if (!entityId) return { factions: [], error: '' }
    const [related, settings] = await Promise.all([
      graphql(`query($id: ID!) { relatedEntities(entityId: $id) { id name type } }`, { id: entityId }),
      roleSettingsByContact(entityId),
    ])
    if (!related) return { factions: [], error: apiError.value || 'Could not load the factions.' }

    const candidates = (related.relatedEntities || [])
      .filter(e => String(e.type).toLowerCase() === 'faction')
    const rosters = await Promise.all(candidates.map(c =>
      graphql(`query($id: ID!) { factionMembers(factionId: $id) { id role rank } }`, { id: c.id })))

    const factions = []
    candidates.forEach((c, i) => {
      const mine = (rosters[i]?.factionMembers || []).find(m => m.id === entityId)
      if (mine) factions.push({ id: c.id, name: c.name, role: mine.role, rank: mine.rank, settingId: settings[c.id] || '' })
    })
    return { factions, error: '' }
  }

  return { roleTraitId, roleSettingsByContact, setRole, removeMembership, factionsFor }
}
