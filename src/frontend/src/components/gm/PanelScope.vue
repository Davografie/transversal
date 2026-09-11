<template>
  <slot />
</template>

<script setup>
import { provide } from 'vue'

// Hands a panel spec's `context` down to the panel's component.
//
// A panel's slot content cannot `provide` to the panel's *child* panels: children
// are rendered by `Panel.vue` (as siblings of the slot outlet), and Vue's
// provide/inject follows the instance chain — the child panel's parent is
// `Panel.vue`, not the slot content. So a parent that needs to hand something
// down (the SFX editor's shared draft, say) puts it in the spec's `context` and
// this wrapper — which *is* the child component's parent — provides it.
//
// Values are provided as given, so pass a stable reference (an instance, a ref,
// a computed). The object is read once at mount; a panel re-opened with the same
// component+id replaces its spec (and so re-mounts with the new context).
const props = defineProps({
  context: { type: Object, default: null },
})

for (const [key, value] of Object.entries(props.context || {})) {
  provide(key, value)
}
</script>
