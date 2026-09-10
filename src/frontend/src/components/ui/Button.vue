<template>
  <button
    :type="type"
    class="btn"
    :class="[`btn-${variant}`, `btn-${size}`, { 'is-loading': loading, 'is-active': active, 'is-block': block }]"
    :disabled="disabled || loading"
    :aria-busy="loading ? 'true' : undefined"
    @click="onClick"
  >
    <span v-if="loading" class="btn-spinner" aria-hidden="true" />
    <span v-else-if="$slots.icon" class="btn-icon"><slot name="icon" /></span>
    <span class="btn-label"><slot /></span>
  </button>
</template>

<script setup>
// Shared button primitive. One component covers the app's button surfaces:
// variant (what it means), size (how big), and the full interaction state set
// (idle / hover / pressed / focus-visible / loading / disabled / active).
//
//   <Button variant="primary" :loading="saving" @click="save">Save</Button>
//   <Button variant="ghost" size="icon" title="Close">×</Button>
//   <Button variant="danger" block :disabled="!canDelete">Delete</Button>
//
// Colors come from the theme tokens, so buttons follow light/dark (and future
// per-universe palettes) automatically. Loading implies disabled; the label
// stays visible so the button doesn't change width mid-action.
const props = defineProps({
  // primary   — the one action a surface wants (accent fill)
  // secondary — default actions (neutral fill)
  // ghost     — low-emphasis / icon buttons (transparent until hover)
  // danger    — destructive (danger tint)
  // success   — confirm/commit (success tint)
  // link      — inline text action (no chrome)
  variant: { type: String, default: 'secondary' },
  size: { type: String, default: 'md' },        // 'sm' | 'md' | 'lg' | 'icon'
  type: { type: String, default: 'button' },    // 'button' | 'submit' | 'reset'
  loading: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  // Toggle/selected state (e.g. an active mode tab) — `is-active` styling.
  active: { type: Boolean, default: false },
  block: { type: Boolean, default: false },     // full width
})

const emit = defineEmits(['click'])

function onClick(e) {
  if (props.disabled || props.loading) return
  emit('click', e)
}
</script>

<style scoped>
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-weight: 600;
  line-height: 1.2;
  border-radius: var(--radius);
  border: 1px solid transparent;
  cursor: pointer;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
  transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease, opacity 0.15s ease;
}
.btn.is-block { width: 100%; }

/* ── Sizes ─────────────────────────────────────────── */
.btn-sm { font-size: 11px; padding: 3px 8px; gap: 4px; border-radius: 5px; }
.btn-md { font-size: 12px; padding: 6px 12px; }
.btn-lg { font-size: 14px; padding: 9px 18px; }
.btn-icon {
  width: 32px; height: 32px;
  padding: 0;
  font-size: 14px;
  flex-shrink: 0;
}

/* ── Variants ──────────────────────────────────────── */
.btn-primary {
  background: var(--accent);
  color: var(--text-on-accent);
}
.btn-primary:hover:not(:disabled) { background: color-mix(in srgb, var(--accent) 88%, var(--text)); }
.btn-primary:active:not(:disabled) { background: color-mix(in srgb, var(--accent) 78%, var(--text)); }

.btn-secondary {
  background: var(--overlay-8);
  border-color: var(--overlay-12);
  color: var(--text);
}
.btn-secondary:hover:not(:disabled) { background: var(--overlay-12); }
.btn-secondary:active:not(:disabled) { background: var(--overlay-15); }

.btn-ghost {
  background: transparent;
  color: var(--text-dim);
}
.btn-ghost:hover:not(:disabled) { background: var(--overlay-8); color: var(--text); }
.btn-ghost:active:not(:disabled) { background: var(--overlay-12); }

.btn-danger {
  background: var(--danger-12);
  border-color: var(--danger-20);
  color: var(--danger);
}
.btn-danger:hover:not(:disabled) { background: var(--danger-20); }
.btn-danger:active:not(:disabled) { background: var(--danger-32); }

.btn-success {
  background: var(--success-12);
  border-color: var(--success-25);
  color: var(--success);
}
.btn-success:hover:not(:disabled) { background: var(--success-25); }
.btn-success:active:not(:disabled) { background: var(--success-32); }

.btn-link {
  background: transparent;
  border: none;
  padding-left: 0;
  padding-right: 0;
  color: var(--accent);
  font-weight: 500;
}
.btn-link:hover:not(:disabled) { text-decoration: underline; }
.btn-link:active:not(:disabled) { color: var(--accent-active); }

/* ── States ────────────────────────────────────────── */
/* Toggle/selected — wins over the variant fill (variant-specific actives
   below keep their hue: an active danger button stays dangerous). */
.btn.is-active {
  background: var(--accent-active);
  border-color: var(--accent-active);
  color: var(--text-on-accent);
}
.btn-danger.is-active {
  background: var(--danger-32);
  border-color: var(--danger-45);
  color: var(--danger);
}
.btn-success.is-active {
  background: var(--success-32);
  border-color: var(--success-45);
  color: var(--success);
}
.btn-secondary.is-active {
  background: var(--accent-12);
  border-color: var(--accent-dim);
  color: var(--accent);
}
.btn-ghost.is-active,
.btn-link.is-active {
  background: var(--accent-12);
  border-color: transparent;
  color: var(--accent);
}

.btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.btn:disabled {
  opacity: 0.45;
  cursor: default;
}

.btn.is-loading {
  cursor: progress;
  opacity: 0.75;
}
/* Keep the label readable but clearly inert while loading. */
.btn.is-loading .btn-label { opacity: 0.85; }

.btn-spinner {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  border: 2px solid currentColor;
  border-top-color: transparent;
  border-radius: 50%;
  animation: btn-spin 0.7s linear infinite;
}
@keyframes btn-spin { to { transform: rotate(360deg); } }

.btn-icon { display: inline-flex; align-items: center; }

/* Respect reduced-motion: no spinner rotation, no transitions. */
@media (prefers-reduced-motion: reduce) {
  .btn { transition: none; }
  .btn-spinner { animation-duration: 1.6s; }
}
</style>
