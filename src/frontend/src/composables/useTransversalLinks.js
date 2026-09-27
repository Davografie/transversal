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

  // `type` is a *query* parameter on the DELETE route (it defaults to `super`),
  // so a transversal link must name itself or the call would look for — and
  // 404 on — a parent edge. The route deletes the reverse edge too, so a link is
  // removed in both directions from the one call.
  async function deleteTransversalLink(fromId, toId) {
    const r = await fetch(`${API_BASE}/locations/${fromId}/edges/${toId}?type=transversal`, {
      method: 'DELETE',
    })
    if (!r.ok) {
      // FastAPI's refusals are JSON (`{"detail": "..."}`), so surface the reason
      // rather than the raw body — a 404 here means the edge was already gone.
      let message = `Could not remove that link (${r.status})`
      try {
        const body = await r.json()
        if (body?.detail) message = body.detail
      } catch {}
      throw new Error(message)
    }
  }

  async function toggleTransversalType(fromId, toId, current) {
    const next = nextTransversalType(current)
    await setTransversalType(fromId, toId, next)
    return next
  }

  return { setTransversalType, createTransversalLink, deleteTransversalLink, toggleTransversalType, nextTransversalType }
}
