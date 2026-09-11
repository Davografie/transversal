<template>
<div class="trait-detail-panel">
  <div class="detail-header">
    <Button class="detail-back" variant="link" @click="$emit('back')">← {{ trait.traitsetName || 'Back' }}</Button>
    <Button class="detail-edit" variant="link" @click="$emit('edit', trait)">✎ Edit</Button>
  </div>

  <div class="detail-hero">
    <div class="detail-hero-line">
      <h3 class="detail-name">{{ api.displayName(trait.name) }}</h3>
      <span class="detail-polarity" :class="{ negative: trait.polarity === 'NEGATIVE' }">● {{ trait.polarity === 'NEGATIVE' ? 'negative' : 'positive' }}</span>
    </div>
    <div class="detail-kicker">
      <span v-if="trait.traitsetName">{{ trait.traitsetName }}</span>
      <span v-if="trait.traitsetName" class="detail-kicker-sep">·</span>
      <span>{{ trait.ego === false ? 'morph' : 'ego' }}</span>
      <span v-if="trait.enabled === false" class="trait-disabled-badge">disabled</span>
    </div>
    <div v-if="trait.tags?.length" class="detail-tags">
      <span v-for="tag in trait.tags" :key="tag" class="detail-tag">{{ tag }}</span>
    </div>
  </div>

  <div
    class="detail-section detail-rating-band"
    :class="{ playable: api.canPlayTrait(trait) }"
    :title="api.canPlayTrait(trait) ? 'Play this trait' : ''"
    @click.stop="api.canPlayTrait(trait) && api.playTrait(trait)"
  >
    <div class="detail-section-head">
      <span class="detail-label">Rating</span>
      <span class="detail-meta">{{ api.ratingTypeLabel(trait) }}</span>
    </div>
    <div class="detail-dice">
      <DieIcon v-for="(die, i) in (trait.dice || [])" :key="i" :die="String(die).toLowerCase()" class="detail-die" />
      <span v-if="api.challengeProgressLabel(trait)" class="challenge-progress">{{ api.challengeProgressLabel(trait) }}</span>
      <span v-if="!(trait.dice || []).length" class="trait-die depleted">unrated</span>
    </div>
    <div v-if="!(trait.dice || []).length" class="trait-die depleted">unrated</div>
    <p v-if="trait.statement" class="detail-statement">{{ trait.statement }}</p>
  </div>

  <div v-if="trait.sfxIds?.length" class="detail-section">
    <div class="detail-section-head"><span class="detail-label">SFX</span></div>
    <div class="sfx-cards">
      <SfxCard v-for="sfxId in trait.sfxIds" :key="sfxId" v-bind="api.sfxCardModel(sfxId)"
               @activate="api.activateSfx(sfxId, trait.id)" />
    </div>
  </div>

  <div v-if="trait.notes" class="detail-section">
    <div class="detail-section-head"><span class="detail-label">Notes</span></div>
    <p class="detail-text">{{ trait.notes }}</p>
  </div>

  <div v-if="(trait.subTraitSettings || []).length" class="detail-section">
    <div class="detail-section-head"><span class="detail-label">Sub-traits</span></div>
    <div class="detail-subtraits">
      <div v-for="st in trait.subTraitSettings" :key="st.id" class="detail-subtrait">
        <span class="detail-subtrait-dice">
          <DieIcon v-for="(die, i) in (st.dice || [])" :key="i" :die="String(die).toLowerCase()" class="detail-die-sm" />
        </span>
        <span class="detail-subtrait-name">{{ api.displayName(st.name) }}</span>
        <Button v-if="api.canPlayTrait(st)" class="detail-subtrait-play" variant="link" @click.stop="api.playTrait(st)">▸ play</Button>
      </div>
    </div>
  </div>

  <div v-if="api.detailContext(trait).length" class="detail-section detail-context">
    <div v-for="row in api.detailContext(trait)" :key="row.label" class="detail-context-row">
      <span class="detail-context-label">{{ row.label }}</span>
      <span class="detail-context-value">{{ row.value }}</span>
    </div>
  </div>
</div>
</template>

<script setup>
import Button from '@/components/ui/Button.vue'
import DieIcon from '@/components/DieIcon.vue'
import SfxCard from './SfxCard.vue'

// The read-only view of one trait: rating band (die faces as text, playable when
// the sheet allows it), SFX cards, notes, sub-traits and the derived context
// rows. The sheet keeps the data + rules, so they arrive as one `api` object of
// functions — helpers, not state, so nothing here needs unwrapping.
defineProps({
  /** The trait being shown (`detailTrait` in the sheet). */
  trait: { type: Object, required: true },
  api: {
    type: Object,
    required: true,
  }, // { canPlayTrait, playTrait, ratingTypeLabel, challengeProgressLabel, detailContext, displayName, sfxCardModel, activateSfx }
})

defineEmits(['back', 'edit'])
</script>

<style scoped>
.trait-detail-panel { display: flex; flex-direction: column; }
.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}
.detail-header .detail-back { padding: 0; font-size: 12px; font-weight: 400; }
.detail-header .detail-edit { padding: 0; font-size: 12px; font-weight: 400; color: var(--text-dim); }
.detail-header .detail-edit:hover { color: var(--accent); }
.detail-hero { margin-bottom: 12px; }
.detail-hero-line { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.detail-name { font-size: 20px; font-weight: 700; margin: 0; color: var(--text); }
.detail-polarity { font-size: 11px; color: var(--success); white-space: nowrap; }
.detail-polarity.negative { color: var(--danger); }
.detail-kicker {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-dim);
}
.detail-kicker-sep { opacity: 0.5; }
.detail-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
.detail-tag {
  font-size: 11px;
  line-height: 1.6;
  padding: 0 8px;
  border-radius: 999px;
  background: var(--accent-12);
  border: 1px solid var(--accent-20);
  color: var(--accent);
}
.detail-section { padding: 10px 0; border-top: 1px solid var(--overlay-8); }
.detail-section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.detail-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-dim);
}
.detail-meta { font-size: 11px; color: var(--text-dim); }
.detail-rating-band.playable { cursor: pointer; }
.detail-rating-band.playable:hover .detail-die { filter: brightness(1.2); }
.detail-dice {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  flex-wrap: wrap;
}
.detail-die { width: 40px; height: 43px; }
.detail-statement {
  margin: 8px 0 0;
  font-size: 13px;
  font-style: italic;
  line-height: 1.4;
  color: var(--text);
}
.detail-subtraits { display: flex; flex-direction: column; gap: 5px; }
.detail-subtrait { display: flex; align-items: center; gap: 8px; }
.detail-subtrait-dice { display: flex; gap: 2px; flex-shrink: 0; }
.detail-die-sm { width: 20px; height: 21px; }
.detail-subtrait-name { flex: 1; min-width: 0; font-size: 12px; color: var(--text); }
.detail-subtrait .detail-subtrait-play {
  padding: 0;
  font-size: 11px;
  font-weight: 400;
  color: var(--text-dim);
  flex-shrink: 0;
}
.detail-subtrait .detail-subtrait-play:hover { color: var(--accent); }
.detail-context { display: flex; flex-direction: column; gap: 2px; }
.detail-context-row { display: flex; gap: 10px; font-size: 11px; }
.detail-context-label { min-width: 68px; color: var(--text-dim); }
.detail-context-value { color: var(--text); }
.detail-text { margin: 0; font-size: 12px; line-height: 1.5; color: var(--text); white-space: pre-wrap; }
.detail-section .sfx-card-rules {
  margin-top: 2px;
  font-size: 11px;
  line-height: 1.35;
  color: var(--text);
}
</style>
