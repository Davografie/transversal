<template>
  <div class="svp-root">
    <p class="svp-hint">
      Names this step supplies to the table it wraps. They resolve <em>before</em> the
      table's own, so a <strong>shared</strong> table reads the context of the path
      walking it — <code>{sect}</code> rather than a hardcoded faction. A name the
      table also declares is shadowed here while this step resolves; tick
      <em>override</em> to replace the table's outright.
    </p>
    <BoundVariablesEditor
      :model-value="draft?.boundVariables || []"
      :variables="baseVariables"
      :types="types"
      :overridable="overridable"
      allow-override
      @update:model-value="onUpdate"
    />
  </div>
</template>

<script setup>
import { computed, inject } from 'vue'
import BoundVariablesEditor from './BoundVariablesEditor.vue'
import { useBoundVariableScope } from '@/composables/useBoundVariableScope.js'

// A **step's** own declaration layer ([[B290]]), edited in a child panel — the same
// reason a step's effects live in one: the step list is already table + label +
// default-next + effects, and a fourth stacked builder is what moved the effects out.
//
// It persists nothing: the step is the **path panel's** live draft, handed across in
// the spec's `context` (a panel cannot `provide` to its own child panels, which are
// rendered as siblings), and the path panel's auto-save writes the whole path.
const draft = inject('rowDraft', null)
// The scope this layer starts from: the ambient roll-table facts plus the **path's**
// own declarations, snapshotted when the panel opened. The path panel is what edits
// those, so they cannot change underneath this child.
const baseVariables = inject('boundVariableBase', {})
// The names the wrapped table declares, so a name that collides with one can say so
// and offer the override rather than looking like any other declaration.
const overridable = inject('boundVariableOverridable', [])

// `inject` must precede this: the composable's watcher is `immediate`, so it reads
// `draft.boundVariables` during setup.
const { types } = useBoundVariableScope(
  computed(() => draft?.boundVariables || []),
  computed(() => baseVariables || {}),
)

function onUpdate(list) {
  if (draft) draft.boundVariables = list
}
</script>

<style scoped>
.svp-root { display: flex; flex-direction: column; gap: 8px; }
.svp-hint { margin: 0; font-size: 10px; color: var(--text-dim); line-height: 1.5; }
.svp-hint code { color: var(--accent-pale); }
</style>
