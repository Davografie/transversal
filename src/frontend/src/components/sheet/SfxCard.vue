<template>
  <div
    class="sfx-card"
    :class="{ 'sfx-active': active, 'sfx-used': used && !active, 'sfx-blocked': blocked }"
    :title="title"
    @click.stop.prevent="!disabled && $emit('activate')"
  >
    <span class="sfx-card-name">{{ name }}</span>
    <span v-if="description" class="sfx-card-desc">{{ description }}</span>
    <span v-if="rules" class="sfx-card-rules">{{ rules }}</span>
  </div>
</template>

<script setup>
// One SFX in a card strip (entity, projection, trait and trait-set grants all
// render the same card). Purely presentational: the sheet resolves the labels
// and the state, and `disabled` reproduces the old click guard — the card does
// not fire when the phase or a condition blocks it. How much text the card
// carries is the host's call, via `sfxCardModel`'s variants: the trait teaser
// gets the name alone, the strips add the description, and only the trait
// detail clickthrough passes the natural-language rules line.
defineProps({
  name: { type: String, default: '' },
  description: { type: String, default: '' },
  rules: { type: String, default: '' },
  title: { type: String, default: '' },
  active: { type: Boolean, default: false },
  used: { type: Boolean, default: false },
  blocked: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})

defineEmits(['activate'])
</script>

<style scoped>
.sfx-card {
  display: flex;
  flex-direction: column;
  gap: 1px;
  align-self: flex-start;
  max-width: 100%;
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid var(--overlay-8);
  background: var(--overlay-2);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.sfx-card:hover {
  border-color: var(--overlay-20);
}
.sfx-card.sfx-active {
  border-color: var(--accent);
  background: var(--accent-12);
}
.sfx-card.sfx-used {
  opacity: 0.35;
  pointer-events: none;
}
.sfx-card.sfx-blocked {
  opacity: 0.45;
  cursor: not-allowed;
  border-style: dashed;
}
.sfx-card-name {
  font-size: 11px;
  font-weight: 600;
  color: var(--text);
}
.sfx-card-desc {
  font-size: 10px;
  color: var(--text-dim);
  line-height: 1.3;
}
/* The derived natural-language rules line inside a detail SFX card. Brighter
   than the flavour lead-in above it — this is the text that tells you what the
   SFX actually does. (Was `.detail-section .sfx-card-rules`; only the detail's
   `'full'` variant carries `rules`, so the nesting is implicit now.) */
.sfx-card-rules {
  margin-top: 2px;
  font-size: 11px;
  line-height: 1.35;
  color: var(--text);
}
</style>
