<template>
  <input
    v-if="editing"
    ref="input"
    v-model="draft"
    class="role-input"
    placeholder="role…"
    @click.stop
    @keyup.enter="commit"
    @keyup.esc="cancel"
    @blur="commit"
  />
  <Button
    v-else
    class="role-chip"
    :class="{ unset: !role }"
    variant="ghost"
    size="sm"
    :loading="busy"
    :title="title"
    @click.stop="start"
  >{{ role || '+ role' }}</Button>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import Button from '@/components/ui/Button.vue'

// One role, inline: the value lives on a membership tie's trait setting and is
// edited from both ends (a faction's roster, an entity's faction list), so the
// edit state machine lives here rather than twice. The write itself belongs to
// `useFactionRoles` — this only reports the new statement.
const props = defineProps({
  role: { type: String, default: '' },
  busy: { type: Boolean, default: false },
  title: { type: String, default: 'Edit this role' },
})

const emit = defineEmits(['save'])

const editing = ref(false)
const draft = ref('')
const input = ref(null)

function start() {
  draft.value = props.role || ''
  editing.value = true
  nextTick(() => input.value?.focus())
}

function cancel() {
  editing.value = false
}

function commit() {
  if (!editing.value) return          // the blur that follows enter/escape
  const next = draft.value.trim()
  editing.value = false
  if (next !== (props.role || '')) emit('save', next)
}
</script>

<style scoped>
/* A chip, not a control row: a role is short text sitting beside a name. */
.role-chip { font-size: 11px; color: var(--text-dim); padding: 1px 6px; }
.role-chip.unset { font-style: italic; opacity: 0.65; }
.role-input { width: 96px; font-size: 11px; padding: 2px 6px; }
</style>
