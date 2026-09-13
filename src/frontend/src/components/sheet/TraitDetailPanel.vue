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
    <div v-if="tagRows.length" class="detail-tags">
      <span
        v-for="row in tagRows"
        :key="row.tag"
        class="detail-tag"
        :class="{ 'detail-tag-inherited': row.inherited }"
        :title="row.inherited ? 'From the trait definition' : 'Set on this trait instance'"
      >{{ row.tag }}</span>
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
    <div class="detail-dice" :title="api.challengeProgressLabel(trait) ? api.challengeProgressLabel(trait) + ' filled' : null">
      <DieIcon v-for="(die, i) in (trait.dice || [])" :key="'f' + i" :die="String(die).toLowerCase()" class="detail-die" />
      <!-- The unfilled capacity of a challenge track, dimmed (see
           challengeRemainingGroups). Not clickable — nothing to spend yet. -->
      <DieIcon v-for="(die, i) in api.challengeRemainingGroups(trait).flat()" :key="'r' + i" :die="die" class="detail-die ghost" />
      <span v-if="!(trait.dice || []).length && !api.challengeRemainingGroups(trait).length" class="trait-die depleted">unrated</span>
    </div>
    <p v-if="trait.statement" class="detail-statement">{{ trait.statement }}</p>
  </div>

  <div v-if="trait.sfxIds?.length" class="detail-section">
    <div class="detail-section-head"><span class="detail-label">SFX</span></div>
    <div class="sfx-cards">
      <SfxCard v-for="sfxId in trait.sfxIds" :key="sfxId" v-bind="api.sfxCardModel(sfxId, 'full')"
               @activate="api.activateSfx(sfxId, trait.id)" />
    </div>
  </div>

  <div v-if="trait.notes" class="detail-section">
    <div class="detail-section-head"><span class="detail-label">Notes</span></div>
    <!-- renderMarkdown escapes HTML before transforming (XSS-safe) and
         allow-lists link URLs. -->
    <div class="detail-notes" v-html="renderMarkdown(trait.notes)"></div>
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
import { computed } from 'vue'
import Button from '@/components/ui/Button.vue'
import { renderMarkdown } from '@/utils/markdown.js'
import DieIcon from '@/components/DieIcon.vue'
import SfxCard from './SfxCard.vue'

// The read-only view of one trait: rating band (die faces as text, playable when
// the sheet allows it), SFX cards, notes, sub-traits and the derived context
// rows. The sheet keeps the data + rules, so they arrive as one `api` object of
// functions — helpers, not state, so nothing here needs unwrapping.
const props = defineProps({
  /** The trait being shown (`detailTrait` in the sheet). */
  trait: { type: Object, required: true },
  api: {
    type: Object,
    required: true,
  }, // { canPlayTrait, playTrait, ratingTypeLabel, challengeProgressLabel, detailContext, displayName, sfxCardModel (variant 'full'), activateSfx }
})

defineEmits(['back', 'edit'])

// Tags arrive in two halves: the ones set on this trait *instance* and the ones
// inherited from the registry trait. Matching sees both, so the panel shows
// both — inherited entries dimmed, since only your own are editable here.
const tagRows = computed(() => {
  const own = props.trait.tags ?? []
  const inherited = (props.trait.registryTags ?? []).filter((t) => !own.includes(t))
  return [
    ...own.map((tag) => ({ tag, inherited: false })),
    ...inherited.map((tag) => ({ tag, inherited: true })),
  ]
})
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
.detail-tag-inherited { opacity: 0.6; border-style: dashed; }
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
/* Unfilled challenge capacity — the same dimming as the row's ghost dice. */
.detail-die.ghost { opacity: 0.32; }
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

/* Notes render as markdown. `:deep()` is required: the tags below are produced
   by `v-html`, and Vue's scoped-CSS compiler puts the scope attribute on the
   *last* selector — so a plain `.detail-notes p { … }` would compile to
   `.detail-notes p[data-v-x]`, and the generated `p` never carries that
   attribute. (BlueBook's `.bb-body` rules have exactly this bug today: their
   markdown renders unstyled.) */
.detail-notes {
  font-size: 12px;
  line-height: 1.5;
  color: var(--text);
  word-wrap: break-word;
}
.detail-notes :deep(p) { margin: 4px 0; }
.detail-notes :deep(h1),
.detail-notes :deep(h2),
.detail-notes :deep(h3),
.detail-notes :deep(h4),
.detail-notes :deep(h5),
.detail-notes :deep(h6) { margin: 8px 0 4px; line-height: 1.3; }
.detail-notes :deep(h1) { font-size: 16px; }
.detail-notes :deep(h2) { font-size: 15px; }
.detail-notes :deep(h3) { font-size: 14px; }
.detail-notes :deep(h4) { font-size: 13px; }
.detail-notes :deep(h5) { font-size: 12px; }
.detail-notes :deep(h6) { font-size: 12px; color: var(--text-dim); }
.detail-notes :deep(ul),
.detail-notes :deep(ol) { margin: 4px 0; padding-left: 20px; }
.detail-notes :deep(li) { margin: 2px 0; }
.detail-notes :deep(code) {
  font-family: monospace;
  font-size: 11px;
  background: var(--overlay-8);
  padding: 1px 4px;
  border-radius: 3px;
}
.detail-notes :deep(pre) {
  background: var(--overlay-8);
  border: 1px solid var(--overlay-12);
  border-radius: 4px;
  padding: 8px;
  overflow-x: auto;
  margin: 6px 0;
}
.detail-notes :deep(pre code) { background: none; padding: 0; }
.detail-notes :deep(blockquote) {
  border-left: 3px solid var(--accent);
  margin: 6px 0;
  padding: 2px 10px;
  color: var(--text-dim);
}
.detail-notes :deep(a) { color: var(--accent); text-decoration: underline; }
.detail-notes :deep(strong) { font-weight: 700; }
.detail-notes :deep(em) { font-style: italic; }
.detail-section .sfx-card-rules {
  margin-top: 2px;
  font-size: 11px;
  line-height: 1.35;
  color: var(--text);
}
</style>
