<template>
  <div class="segmented" role="radiogroup" :aria-label="ariaLabel">
    <button
      v-for="o in options"
      :key="String(o.value)"
      type="button"
      class="segmented-btn"
      role="radio"
      :class="{ active: o.value === modelValue }"
      :aria-checked="o.value === modelValue"
      :title="o.title || ''"
      :disabled="o.disabled"
      @click="select(o.value)"
      @keydown.left.prevent="step(-1)"
      @keydown.right.prevent="step(1)"
      @keydown.up.prevent="step(-1)"
      @keydown.down.prevent="step(1)"
    >{{ o.label }}</button>
  </div>
</template>

<script setup>
/**
 * Segmented control — a small set of mutually exclusive, always-visible
 * choices (mode, media quality, die/variable, …). Deliberately **not** a
 * `Button`: the segments keep an equal width and read as one object, so they
 * own their chrome instead of borrowing a button variant (see
 * [[UI-UX Design#SegmentedControl]]).
 *
 * Keyboard: it is a radiogroup — arrows move the selection, clicks select
 * directly. Values may be strings, numbers, booleans or null.
 */
const props = defineProps({
  modelValue: { type: [String, Number, Boolean], default: null },
  /** [{ value, label, title?, disabled? }] */
  options: { type: Array, required: true },
  ariaLabel: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue'])

function select(value) {
  if (value !== props.modelValue) emit('update:modelValue', value)
}

function step(delta) {
  const enabled = props.options.filter((o) => !o.disabled)
  if (enabled.length < 2) return
  const at = enabled.findIndex((o) => o.value === props.modelValue)
  const next = enabled[(at + delta + enabled.length) % enabled.length]
  if (next) select(next.value)
}
</script>

<style scoped>
.segmented {
  display: flex;
  gap: 0;
  width: 100%;
  border: 1px solid var(--overlay-10);
  border-radius: 6px;
  overflow: hidden;
}
.segmented-btn {
  flex: 1;
  padding: 8px 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--text-dim);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.segmented-btn:hover:not(.active) { background: var(--overlay-6); color: var(--text); }
.segmented-btn.active {
  background: var(--accent-active);
  color: var(--text-on-accent);
}
.segmented-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.segmented-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
</style>
