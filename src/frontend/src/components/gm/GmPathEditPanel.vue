<template>
  <div class="pe-root">
    <TargetSpecBuilder
      v-if="model"
      v-model="model"
      :destination="destination"
      :source-element="sourceElement"
      :variables="variables"
      :title="title"
      :boolean-terminal="booleanTerminal"
      @resolve="emit('resolve', $event)"
    />
    <p v-else class="pe-missing">
      This panel was opened without a path to edit. Close it and use the field's
      <strong>Edit path</strong> button.
    </p>
  </div>
</template>

<script setup>
import { computed, inject } from 'vue'
import TargetSpecBuilder from './TargetSpecBuilder.vue'

// The child-panel host for one targeting path. It exists so the path can be
// edited *away* from the form it belongs to: a builder is tall (a step per row,
// each with its own controls), and a condition or effect that carries one made
// the whole panel scroll. Opened by `PathField`, which owns the summary and the
// button; this side only provides the room.
//
// `resolve` is forwarded verbatim: an effect reads where its path *landed* (a
// rating die can be timed, a pool die cannot), and the panel spec's `listeners`
// bind to this component, not to the builder inside it.
const emit = defineEmits(['resolve'])

const props = defineProps({
  destination: { type: Object, default: null },
  sourceElement: { type: String, default: '' },
  variables: { type: Object, default: null },
  title: { type: String, default: 'Targeting path' },
  booleanTerminal: { type: Boolean, default: false },
})

// The path being edited, handed across in the panel spec's `context` as a
// `{ get, set }` pair (see `PanelScope`). A get/set pair rather than a ref
// because a *plain object* crosses the provide/inject boundary with no
// ref-unwrapping surprises on either side — and a write here re-emits on the
// parent, so the editor and the rule are the same object.
const binding = inject('pathBinding', null)

const model = computed({
  get: () => (binding ? binding.get() : null),
  set: (v) => { if (binding) binding.set(v) },
})
</script>

<style scoped>
.pe-root { display: flex; flex-direction: column; gap: 6px; }
.pe-missing { margin: 0; font-size: 11px; color: var(--text-dim); }
</style>
