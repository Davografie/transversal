<template>
  <div class="reach-root">
    <!-- Each row is one way this rule reaches owners: a targeting path that
         **yields** them, plus the relationship. The path is the offer or the
         grant — there is no gate narrowing a candidate list any more
         ([[Dynamic SFX Reach]]). -->
    <div v-for="(row, i) in rows" :key="i" class="reach-row">
      <div class="reach-row-head">
        <SegmentedControl
          class="reach-flavour"
          :model-value="flavourOf(row)"
          :options="FLAVOURS"
          aria-label="Relationship"
          @update:model-value="onFlavour(i, $event)"
        />
        <Button
          class="reach-remove"
          variant="danger-ghost"
          size="sm"
          title="Remove this path"
          @click="remove(i)"
        >✕</Button>
      </div>
      <PathField
        :model-value="row.spec"
        :destination="destination"
        :source-element="sourceElement"
        :allow-source="false"
        title="Reach path"
        @update:model-value="onSpec(i, $event)"
      />
      <p class="reach-why">{{ why(row) }}</p>
    </div>

    <Button class="reach-add" variant="secondary" size="sm" @click="add">+ Add reach</Button>

    <p v-if="!rows.length" class="reach-empty">
      Nothing reaches this rule yet, so it appears only where it is attached. Add a
      path to say who simply <em>has</em> it, or who is <em>offered</em> it.
    </p>
    <!-- The one thing the author must know before a path is worth building: the
         rule's `Source` decides the element every path has to land on, so a path
         that ends elsewhere is not a reach declaration at all. -->
    <p v-if="rows.length && !sourceElement" class="reach-note reach-note-warn">
      Set <strong>Lives on</strong> first — it decides the element every path here
      must land on, and it types the wizard while you build.
    </p>
    <p v-else-if="rows.length" class="reach-note">
      Every path must land on <strong>{{ elementName }}</strong> — this rule's source.
      A path starts from a <em>collection</em> (<code>traits</code>, <code>entities</code>,
      <code>traitsets</code>, …): a reach declaration has no source of its own, so
      <code>select source</code> is not offered here. Paths are OR-ed, and where an owner
      is both given and offered the rule, having it wins.
    </p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import Button from '@/components/ui/Button.vue'
import SegmentedControl from '@/components/ui/SegmentedControl.vue'
import PathField from './PathField.vue'
import { useTargetCatalog } from '@/composables/useTargetCatalog.js'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  // The element the rule's `Source` resolves to: what every path must land on.
  sourceElement: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue'])

const { elementLabel } = useTargetCatalog()

const FLAVOURS = [
  {
    value: 'granted',
    label: 'Has it',
    title: 'Every owner this path selects simply has the rule — available from them, no learn-chip, nothing written on them.',
  },
  {
    value: 'offered',
    label: 'Offered',
    title: 'Every owner this path selects is offered the rule as a learn-chip, which they may take.',
  },
]

const rows = computed(() => props.modelValue || [])
const elementName = computed(() => elementLabel(props.sourceElement) || props.sourceElement)

// The destination is the *only* type constraint a reach path has, and it comes
// from the source — so the builder can refuse a path that ends somewhere else.
// No cardinality: one owner (`literal`) and many (`select locations`) are both
// legitimate declarations.
const destination = computed(() =>
  (props.sourceElement ? { elements: [props.sourceElement] } : null))

function flavourOf(row) {
  return row?.flavour === 'granted' ? 'granted' : 'offered'
}

function why(row) {
  return flavourOf(row) === 'granted'
    ? 'They simply have it — no chip to take.'
    : 'They are offered it as a learn-chip they may take.'
}

function replace(i, next) {
  const list = [...rows.value]
  list[i] = { ...list[i], ...next }
  emit('update:modelValue', list)
}

function onSpec(i, spec) { replace(i, { spec }) }
function onFlavour(i, flavour) { replace(i, { flavour }) }

function add() {
  // Offered is the default: it is the gentler of the two, and the one the static
  // `possibleSfxIds` declaration has always meant.
  emit('update:modelValue', [...rows.value, { spec: { steps: [] }, flavour: 'offered' }])
}

function remove(i) {
  emit('update:modelValue', rows.value.filter((_row, j) => j !== i))
}
</script>

<style scoped>
.reach-root { display: flex; flex-direction: column; gap: 8px; }
.reach-row {
  display: flex; flex-direction: column; gap: 6px;
  padding: 8px; border: 1px solid var(--overlay-10); border-radius: 6px;
  background: var(--overlay-4);
}
.reach-row-head { display: flex; align-items: center; gap: 6px; }
/* `SegmentedControl` is full-width by design; here it shares the row with the
   remove button, so it is given a bounded share instead. */
.reach-flavour { flex: 1; min-width: 0; }
.reach-remove { flex: none; }
.reach-why { margin: 0; font-size: 10px; color: var(--text-dim); }
.reach-note { margin: 0; font-size: 10px; color: var(--text-dim); }
.reach-note-warn { color: var(--warn); }
.reach-empty { margin: 0; font-size: 11px; color: var(--text-dim); }
.reach-add { align-self: flex-start; }
</style>
