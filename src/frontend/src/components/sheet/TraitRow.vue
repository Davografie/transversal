<template>
  <div v-if="api.isKnown(trait)" class="trait-row" :class="{ wrap, morph: trait.ego === false, 'in-pool': api.isInPool(trait), offered: api.isOffered(trait), 'limit-reached': limitReached && !api.isInPool(trait), negative: trait.polarity === 'NEGATIVE', 'trait-disabled': trait.enabled === false }" @click="api.openTraitDetail(trait)" @contextmenu.prevent="api.startEdit(trait)" @touchstart="api.onTouchStart(trait)" @touchend="api.onTouchEnd" @touchmove="api.onTouchEnd">
    <div class="trait-left">
      <span class="trait-name" :class="{ disabled: phase !== 'adding' || api.isResourceDepleted(trait) }">{{ api.displayName(trait.name) }}</span>
      <span v-if="api.traitTimerLabel(trait)" class="trait-timer" :title="'Re-enables after ' + api.traitTimerLabel(trait)">⏳ {{ api.traitTimerLabel(trait) }}</span>
      <span v-if="trait.enabled === false" class="trait-disabled-badge">disabled</span>
      <span v-if="trait.fromType === 'relationship' && trait.relationshipContactName" class="trait-contact">→ {{ trait.relationshipContactName }}</span>
      <span v-if="trait.statement" class="trait-statement">{{ trait.statement }}</span>
      <span v-if="trait.notes" class="trait-notes">{{ trait.notes }}</span>
      <div v-if="trait.sfxIds?.length" class="sfx-cards">
        <SfxCard v-for="sfxId in trait.sfxIds" :key="sfxId" v-bind="api.sfxCardModel(sfxId, 'chip')"
                 @activate="api.activateSfx(sfxId, trait.id)" />
      </div>
    </div>
    <div class="trait-right" @click.stop="api.playTrait(trait)" :title="'Play ' + api.displayName(trait.name)">
      <div v-if="api.traitDiceGroups(trait).length" class="trait-die-groups">
        <div v-for="(group, gi) in api.traitDiceGroups(trait)" :key="gi" class="trait-die-group">
          <DieIcon
            v-for="(die, i) in group"
            :key="i"
            :die="die"
            class="trait-die-icon"
            :style="i ? { marginLeft: '-20px', marginTop: `${i * 4}px` } : null"
          />
        </div>
      </div>
      <div v-else-if="trait.ratingType === 'RESOURCE'" class="trait-die-groups resource">
        <div
          v-for="(group, gi) in api.resourceDiceGroups(trait)"
          :key="'a' + gi"
          class="trait-die-group clickable"
          :title="`Add ${group[0]} to pool`"
          @click.stop="api.spendResourceGroup(trait, group[0])"
        >
          <DieIcon
            v-for="(die, i) in group"
            :key="i"
            :die="die"
            class="trait-die-icon"
            :style="i ? { marginLeft: '-20px', marginTop: `${i * 4}px` } : null"
          />
        </div>
        <div v-for="(group, gi) in api.resourceSpentGroups(trait)" :key="'s' + gi" class="trait-die-group">
          <DieIcon
            v-for="(die, i) in group"
            :key="i"
            :die="die"
            class="trait-die-icon ghost"
            :style="i ? { marginLeft: '-20px', marginTop: `${i * 4}px` } : null"
          />
        </div>
        <span v-if="!(trait.dice || []).length && !(trait.spentDice || []).length" class="trait-die depleted">depleted</span>
      </div>
      <div v-else-if="trait.ratingType === 'CHALLENGE'" class="trait-die-groups challenge">
        <div
          v-for="(group, gi) in api.resourceDiceGroups(trait)"
          :key="'c' + gi"
          class="trait-die-group clickable"
          :title="`Spend ${group[0]} from challenge pool`"
          @click.stop="api.spendChallengeGroup(trait, group[0])"
        >
          <DieIcon
            v-for="(die, i) in group"
            :key="i"
            :die="die"
            class="trait-die-icon"
            :style="i ? { marginLeft: '-20px', marginTop: `${i * 4}px` } : null"
          />
        </div>
        <span v-if="api.challengeProgressLabel(trait)" class="challenge-progress">{{ api.challengeProgressLabel(trait) }}</span>
        <span v-if="!(trait.dice || []).length" class="trait-die depleted">empty</span>
      </div>
      <span v-else class="trait-die" :class="`die-${api.resolvedDieType(trait)}`">{{ api.resourceDisplay(trait) }}</span>
    </div>
  </div>
  <div v-else class="trait-row unknown-trait" :class="{ wrap }">
    <div class="trait-left">
      <span class="trait-name unknown">???</span>
    </div>
    <div class="trait-right">
      <span class="trait-die unknown-die">?</span>
    </div>
  </div>
  <div v-if="api.isKnown(trait) && (trait.subTraitSettings || []).length" class="sub-trait-list">
    <div
      v-for="st in trait.subTraitSettings"
      :key="st.id"
      class="sub-trait-row"
      :class="{ 'in-pool': api.isInPool(st), negative: st.polarity === 'NEGATIVE', 'trait-disabled': st.enabled === false }"
      @click="api.openTraitDetail(st)"
      @contextmenu.prevent
    >
      <div class="sub-trait-left">
        <span class="sub-trait-name" :class="{ disabled: phase !== 'adding' || st.enabled === false }">{{ api.displayName(st.name) }}</span>
        <span v-if="st.statement" class="sub-trait-statement">{{ st.statement }}</span>
      </div>
      <div class="sub-trait-right" @click.stop="api.playTrait(st)" :title="'Play ' + api.displayName(st.name)">
        <div v-if="api.traitDiceGroups(st).length" class="trait-die-groups">
          <div v-for="(group, gi) in api.traitDiceGroups(st)" :key="gi" class="trait-die-group">
            <DieIcon
              v-for="(die, i) in group"
              :key="i"
              :die="die"
              class="trait-die-icon sub-trait-die"
              :style="i ? { marginLeft: '-12px' } : null"
            />
          </div>
        </div>
        <span v-else-if="st.ratingType !== 'EMPTY'" class="trait-die" :class="`die-${api.resolvedDieType(st)}`">{{ api.resourceDisplay(st) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
// A single trait-list item: the known trait row, the unknown ("???") row, and
// the sub-trait list that hangs under a trait. Presentational — every helper
// and every interaction arrives through `api` (functions only), matching the
// detail panel's contract. `wrap` is the profile view's chip layout.
import DieIcon from '@/components/DieIcon.vue'
import SfxCard from './SfxCard.vue'

defineProps({
  trait: { type: Object, required: true },
  api: { type: Object, required: true },
  phase: { type: String, default: '' },
  limitReached: { type: Boolean, default: false },
  wrap: { type: Boolean, default: false },
})
</script>

<style scoped>
/* Trait-row styles moved verbatim from CharacterSheet.vue (B46).
   Order matters: `.trait-row.wrap` (the profile view's chip layout) must sit
   before in-pool/offered/hover/morph/negative — exactly the order the rules had
   in the sheet — so those states keep winning ties as they did there. */

.trait-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 8px;
  /* margin: 0 -8px; */
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.1s;
}

.trait-row.wrap {
  margin: 0;
  flex: 0 0 auto;
  max-width: 100%;
  background: var(--overlay-2);
}

.trait-row.in-pool {
  background: var(--accent-12);
  box-shadow: inset 2px 0 0 var(--accent);
}

.trait-row.offered {
  background: var(--offered-12);
  box-shadow: inset 2px 0 0 var(--offered);
}

.trait-row.limit-reached {
  opacity: 0.3;
  cursor: default;
  pointer-events: none;
}

.unknown-trait {
  cursor: default;
  opacity: 0.4;
}

.trait-name.unknown {
  font-style: italic;
  letter-spacing: 2px;
}

.unknown-die {
  font-weight: 700;
  font-size: 14px;
  color: var(--text-dim);
}

.trait-row:hover {
  background: var(--overlay-4);
}

.trait-row.morph {
  background: var(--accent-8);
  border-left: 2px solid var(--accent);
}

.trait-row.wrap .trait-left {
  flex: 0 1 auto;
}

.trait-left {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.trait-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  flex-shrink: 0;
}

.trait-name {
  cursor: pointer;
  transition: color 0.15s;
  font-weight: 500;
}

.trait-name:hover {
  color: var(--accent);
}

.trait-name.disabled {
  cursor: default;
  opacity: 0.5;
}

.trait-name.disabled:hover {
  color: inherit;
}

.trait-timer {
  font-size: 10px;
  color: var(--accent, #d9b45a);
  margin-left: 6px;
  white-space: nowrap;
}

.trait-disabled {
  opacity: 0.45;
}

.trait-contact {
  font-size: 11px;
  color: var(--text-dim);
  margin-left: 4px;
}

.trait-statement {
  font-size: 10px;
  color: var(--text-dim);
  font-style: italic;
  line-height: 1.3;
}

.trait-notes {
  font-size: 10px;
  color: var(--text-dim);
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.trait-die-groups {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.trait-die-group {
  display: flex;
  align-items: flex-start;
}

.trait-die-group.clickable { cursor: pointer; }

.trait-die-group.clickable:hover .trait-die-icon { filter: brightness(1.25); }

.trait-die-icon {
  width: 32px;
  height: 34px;
}

.trait-die-icon.ghost {
  opacity: 0.32;
}

.sub-trait-list {
  margin: 0 0 4px 20px;
  padding-left: 8px;
  border-left: 2px solid var(--overlay-10);
}

.sub-trait-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 5px;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.1s;
}

.sub-trait-row:hover {
  background: var(--overlay-4);
}

.sub-trait-row.in-pool {
  background: var(--accent-12);
  box-shadow: inset 2px 0 0 var(--accent);
}

.sub-trait-row.negative {
  border-left: 2px solid var(--offered, #f2908a);
}

.sub-trait-row.trait-disabled {
  opacity: 0.45;
}

.sub-trait-left {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.sub-trait-name {
  font-weight: 500;
}

.sub-trait-name.disabled {
  opacity: 0.5;
}

.sub-trait-statement {
  font-size: 11px;
  opacity: 0.75;
}

.sub-trait-right {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 2px;
}

.sub-trait-die {
  font-size: 12px;
}

.trait-row.negative {
  --die-d4: var(--die-d4-neg);
  --die-d6: var(--die-d6-neg);
  --die-d8: var(--die-d8-neg);
  --die-d10: var(--die-d10-neg);
  --die-d12: var(--die-d12-neg);
  background: color-mix(in srgb, var(--die-d8-neg) 10%, transparent);
}

.trait-row.negative.morph {
  background: color-mix(in srgb, var(--die-d8-neg) 14%, transparent);
  border-left: 2px solid var(--die-d8-neg);
}
</style>
