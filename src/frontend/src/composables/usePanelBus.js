// A small typed event bus for GM panel cross-panel communication.
// Replaces window.dispatchEvent('lifepath-saved') with a named, importable
// channel that doesn't leak onto the global window object.
const listeners = new Map()

function on(event, handler) {
  if (!listeners.has(event)) listeners.set(event, new Set())
  listeners.get(event).add(handler)
  return () => off(event, handler)
}

function off(event, handler) {
  const set = listeners.get(event)
  if (set) set.delete(handler)
}

function emit(event, payload) {
  const set = listeners.get(event)
  if (set) set.forEach((handler) => handler(payload))
}

export function usePanelBus() {
  return { on, off, emit }
}
