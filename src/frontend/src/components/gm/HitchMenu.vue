<template>
  <div class="hm-root">
    <div class="hm-title">Buy hitches · {{ count }} selected</div>
    <EntryPicker
      :options="visibleOptions"
      :loading="loading"
      :busy="applying"
      empty-text="No hitch SFX available"
      @pick="apply"
      @close="$emit('close')"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import EntryPicker from '@/components/ui/EntryPicker.vue'
import { useHitchMenu } from '@/composables/useHitchMenu.js'

const props = defineProps({
  entityId: { type: String, required: true },
  buyerId: { type: String, default: '' },
  count: { type: Number, default: 0 },
  side: { type: String, default: 'either' },  // 'gm' | 'player' | 'either'
})
const emit = defineEmits(['apply', 'close'])

const { loading, fetchHitchMenu } = useHitchMenu()
const options = ref([])
const applying = ref(false)

// Only show options available to this viewer: its own bucket plus shared.
const visibleOptions = computed(() =>
  options.value.filter(o => o.side === 'either' || o.side === props.side)
)

onMounted(async () => {
  options.value = await fetchHitchMenu(props.entityId, props.buyerId)
})

async function apply(opt) {
  applying.value = true
  try {
    emit('apply', opt)
  } finally {
    applying.value = false
  }
}
</script>

<style scoped>
.hm-root { display: flex; flex-direction: column; gap: 6px; padding: 8px; background: var(--overlay-2); border: 1px solid var(--overlay-8); border-radius: 6px; }
.hm-title { font-size: 10px; font-weight: 600; color: var(--accent); text-transform: uppercase; letter-spacing: 0.5px; }
/* The option rows, the loading/empty state and the cancel button now come from
   ui/EntryPicker — see [[UI-UX Design#Entry picker]]. */
</style>
