// Shared transversal-edge type toggle. Used by the location viewer navdots,
// the relational canvas edges, and the location entity edit panel.

const API_BASE = '/api/v1'

// Unset behaves as inapposite (the travel effect's default), so toggling from
// an unset/inapposite edge goes to consciousness.
export function nextTransversalType(current) {
  return current === 'consciousness' ? 'inapposite' : 'consciousness'
}

export function useTransversalLinks() {
  async function setTransversalType(fromId, toId, type) {
    const r = await fetch(`${API_BASE}/locations/${fromId}/edges/${toId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'transversal', transversal_type: type }),
    })
    if (!r.ok) throw new Error(await r.text())
    return type
  }

  async function createTransversalLink(fromId, toId) {
    const r = await fetch(`${API_BASE}/locations/${fromId}/edges/${toId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'transversal' }),
    })
    if (!r.ok) throw new Error(await r.text())
  }

  async function toggleTransversalType(fromId, toId, current) {
    const next = nextTransversalType(current)
    await setTransversalType(fromId, toId, next)
    return next
  }

  return { setTransversalType, createTransversalLink, toggleTransversalType, nextTransversalType }
}
