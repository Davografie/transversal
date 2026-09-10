<template>
  <SearchDropdown
    :options="options"
    :model-value="modelValue"
    value-key="key"
    label-key="name"
    :clearable="clearable"
    :placeholder="placeholder"
    @select="pick"
    @clear="$emit('update:modelValue', '')"
  />
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import SearchDropdown from '@/components/ui/SearchDropdown.vue'
import { useApi } from '@/composables/useApi.js'

// Universe picker that emits a universe *key* (current_universe), not the
// universe entity id — the value the IN_UNIVERSE condition and universe scope
// compare against. Universe entity ids are separate synthetic keys.
const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: 'Choose universe…' },
  clearable: { type: Boolean, default: true },
})

const emit = defineEmits(['update:modelValue'])
const { graphql } = useApi()
const universes = ref([])

const options = computed(() =>
  universes.value
    .map((u) => ({ key: u.currentUniverse, name: u.name }))
    .filter((u) => u.key)
    .sort((a, b) => a.name.localeCompare(b.name))
)

onMounted(async () => {
  const data = await graphql(`{ entities(type: UNIVERSE) { id name currentUniverse } }`)
  universes.value = data?.entities || []
})

function pick(opt) {
  emit('update:modelValue', opt.key)
}
</script>
