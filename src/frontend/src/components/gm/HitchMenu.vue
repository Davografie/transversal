<template>
  <div class="hm-root">
    <div class="hm-title">Buy hitches · {{ count }} selected</div>
    <div v-if="options.length" class="hm-menu">
      <button
        v-for="opt in options"
        :key="opt.id"
        class="hm-option"
        :disabled="applying"
        @click="apply(opt)"
      >
        {{ opt.label }}
      </button>
    </div>
    <div v-else-if="loading" class="hm-empty">Loading…</div>
    <div v-else class="hm-empty">No hitch SFX available</div>
    <button class="hm-cancel" @click="$emit('close')">Cancel</button>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useHitchMenu } from '@/composables/useHitchMenu.js'

const props = defineProps({
  entityId: { type: String, required: true },
  count: { type: Number, default: 0 },
})
const emit = defineEmits(['apply', 'close'])

const { loading, fetchHitchMenu } = useHitchMenu()
const options = ref([])
const applying = ref(false)

onMounted(async () => {
  options.value = await fetchHitchMenu()
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
.hm-root { display: flex; flex-direction: column; gap: 6px; padding: 8px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; }
.hm-title { font-size: 10px; font-weight: 600; color: var(--accent); text-transform: uppercase; letter-spacing: 0.5px; }
.hm-menu { display: flex; flex-direction: column; gap: 4px; }
.hm-option { padding: 7px 9px; border-radius: 4px; cursor: pointer; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); color: var(--text); font-size: 11px; text-align: left; }
.hm-option:hover { background: rgba(0,200,150,0.1); border-color: var(--accent); }
.hm-option:disabled { opacity: 0.5; cursor: default; }
.hm-empty { font-size: 10px; color: var(--text-dim); }
.hm-cancel { align-self: flex-start; font-size: 10px; padding: 4px 10px; border-radius: 4px; cursor: pointer; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: var(--text-dim); }
</style>
