<template>
  <div class="ee-root">
    <GmList
      :items="effects"
      reorderable
      drag-handle
      empty-text="No effects defined"
      :row-class="rowClassFn"
      @click="(eff, i) => emit('edit', i)"
      @reorder="onReorder"
    >
      <template #item="{ item: eff, index: i }">
        <span class="ee-cat" :class="'cat-' + effectCategory(eff)">{{ categorySign(effectCategory(eff)) }}</span>
        <span class="ee-summary">{{ effectSummary(eff) }}</span>
        <span class="ee-timing">{{ eff.timing }}</span>
        <Button class="ee-del" variant="danger-ghost" size="sm" @click.stop="removeEffect(i)" title="Remove">✕</Button>
      </template>
    </GmList>

    <Button class="ee-add" variant="secondary" block @click="emit('add')">+ Add effect</Button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useEffectActions } from '@/composables/useEffectActions.js'
import GmList from '@/components/ui/GmList.vue'
import Button from '@/components/ui/Button.vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  editingIndex: { type: Number, default: null },
})
const emit = defineEmits(['update:modelValue', 'add', 'edit'])

const effects = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const { load, actions: effectActions, summarize: effectSummary } = useEffectActions()
load()

function effectCategory(eff) {
  const meta = effectActions.value.find(a => a.effectType === eff.type && a.effectAction === eff.action)
  return meta?.category || 'either'
}
function categorySign(cat) {
  if (cat === 'cost') return '−'
  if (cat === 'benefit') return '+'
  return '~'
}

function removeEffect(i) {
  const next = [...props.modelValue]
  next.splice(i, 1)
  emit('update:modelValue', next)
}

function onReorder(from, to) {
  const next = [...props.modelValue]
  const [moved] = next.splice(from, 1)
  next.splice(to, 0, moved)
  emit('update:modelValue', next)
}

function rowClassFn(eff) {
  return props.editingIndex !== null && props.modelValue[props.editingIndex] === eff ? 'editing' : ''
}
</script>

<style scoped>
.ee-root { display: flex; flex-direction: column; gap: 4px; }
.ee-cat { font-weight: 700; font-size: 11px; width: 18px; text-align: center; }
.cat-cost { color: var(--danger); }
.cat-benefit { color: var(--success); }
.cat-either { color: var(--text-dim); }
.ee-summary { flex: 1; font-family: monospace; font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ee-timing { font-size: 9px; color: var(--text-dim); }
/* "+ Add effect" keeps its deliberate dashed accent (the row is full width via
   the column flex parent); fill/radius/padding/hover come from ui/Button. */
.ee-root > .ee-add { border-style: dashed; border-color: var(--overlay-15); }
</style>
