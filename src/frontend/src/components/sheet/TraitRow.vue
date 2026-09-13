<template>
  <div v-if="depth === 0 && api.isKnown(trait)" class="trait-row" :class="{ wrap, morph: trait.ego === false, container: api.isContainer(trait), 'in-pool': api.isInPool(trait), offered: api.isOffered(trait), 'limit-reached': limitReached && !api.isInPool(trait), negative: trait.polarity === 'NEGATIVE', 'trait-disabled': trait.enabled === false, 'drag-over': api.isDragOver(trait), dragging: api.isDragging(trait) }" :data-ts-id="trait.id" :data-drop-container="api.isContainer(trait) ? trait.id : null" @click="onRowClick" @contextmenu.prevent="api.startEdit(trait)" @touchstart="api.onTouchStart(trait)" @touchend="api.onTouchEnd" @touchmove="api.onTouchEnd" @dragover.prevent="api.onTraitDragOver($event)" @dragleave="api.onTraitDragLeave()" @drop.prevent="api.onTraitDrop($event)" @dragend="api.onTraitDragEnd()">
    <!-- The grip exists only in a set that holds a container — outside one there
         is nowhere to drop, so it would be chrome with no purpose. The GM tree
         resolves the same conflict the same way: a dedicated handle, instant
         drag, leaving long-press free for the row's own action (here: edit). -->
    <span
      v-if="api.canDrag(trait, depth, insideContainer)"
      class="trait-drag-handle"
      draggable="true"
      title="Drag into a container"
      @click.stop
      @touchstart.stop="api.onGripTouchStart($event, trait)"
      @dragstart="api.onTraitDragStart($event, trait)"
      @dragend="api.onTraitDragEnd()"
    >⠿</span>
    <div class="trait-left" :class="{ 'has-statement': !!trait.statement }">
      <span class="trait-name" :class="{ disabled: phase !== 'adding' || api.isResourceDepleted(trait) }" @click.stop="api.openTraitDetail(trait)">{{ api.displayName(trait.name) }}</span>
      <span v-if="api.traitTimerLabel(trait)" class="trait-timer" :title="'Re-enables after ' + api.traitTimerLabel(trait)">⏳ {{ api.traitTimerLabel(trait) }}</span>
      <span v-if="trait.enabled === false" class="trait-disabled-badge">disabled</span>
      <span v-if="trait.fromType === 'relationship' && trait.relationshipContactName" class="trait-contact">→ {{ trait.relationshipContactName }}</span>
      <span v-if="trait.statement" class="trait-statement">{{ trait.statement }}</span>
      <div v-if="trait.sfxIds?.length" class="sfx-cards">
        <SfxCard v-for="sfxId in trait.sfxIds" :key="sfxId" v-bind="api.sfxCardModel(sfxId, 'chip')"
                 @activate="api.activateSfx(sfxId, trait.id)" />
      </div>
    </div>
    <!-- A container is a trait like any other, so its right zone keeps whatever
         rating it has (one instance of the container trait in the live data is
         a static d6 — a container *may* be rated). The disclosure is added
         below it, and only when there is something to disclose: an empty
         container is the default state right after tagging, and a chevron that
         opens nothing is a dead affordance. Without contents this cell renders
         exactly like any other trait. -->
    <div v-if="api.isContainer(trait)" class="trait-right container-cell">
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
      <span v-else-if="trait.ratingType !== 'EMPTY'" class="trait-die" :class="`die-${api.resolvedDieType(trait)}`">{{ api.resourceDisplay(trait) }}</span>
      <div v-if="api.hasContents(trait)" class="container-toggle">
        <Button
          variant="ghost"
          size="icon"
          :title="api.isExpanded(trait) ? 'Hide contents' : 'Show contents'"
          :aria-expanded="api.isExpanded(trait) ? 'true' : 'false'"
          :aria-controls="childrenListId"
          @click.stop="api.toggleExpand(trait)"
        >
          <span class="container-chevron" :class="{ open: api.isExpanded(trait) }">▶</span>
        </Button>
        <span class="container-count">{{ api.containerCount(trait) }}</span>
      </div>
    </div>
    <div v-else class="trait-right" @click.stop="api.playTrait(trait)" :title="'Play ' + api.displayName(trait.name)">
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
  <div v-else-if="depth === 0" class="trait-row unknown-trait" :class="{ wrap }">
    <div class="trait-left">
      <span class="trait-name unknown">???</span>
    </div>
    <div class="trait-right">
      <span class="trait-die unknown-die">?</span>
    </div>
  </div>
  <!-- A nested row (depth > 0). Same markup the sub-trait list always had —
       the difference is that it is now reachable at any depth. -->
  <div
    v-else
    class="sub-trait-row"
    :class="{ 'in-pool': api.isInPool(trait), negative: trait.polarity === 'NEGATIVE', 'trait-disabled': trait.enabled === false, container: api.isContainer(trait), 'drag-over': api.isDragOver(trait), dragging: api.isDragging(trait) }"
    :data-ts-id="trait.id"
    :data-drop-container="api.isContainer(trait) ? trait.id : null"
    @click="onRowClick"
    @contextmenu.prevent
    @dragover.prevent="api.onTraitDragOver($event)"
    @dragleave="api.onTraitDragLeave()"
    @drop.prevent="api.onTraitDrop($event)"
    @dragend="api.onTraitDragEnd()"
  >
    <!-- A row directly inside a container carries a grip, so it can be pulled
         back OUT. Dropping it on any non-container row does that (see the
         sheet's resolveTarget). Deeper rows get none: a sub-trait of a sub-trait
         is part of its parent and stays put. -->
    <span
      v-if="api.canDrag(trait, depth, insideContainer)"
      class="trait-drag-handle sub-trait-grip"
      draggable="true"
      title="Drag out of this container"
      @click.stop
      @touchstart.stop="api.onGripTouchStart($event, trait)"
      @dragstart="api.onTraitDragStart($event, trait)"
      @dragend="api.onTraitDragEnd()"
    >⠿</span>
    <div class="sub-trait-left" :class="{ 'has-statement': !!trait.statement }">
      <span class="sub-trait-name" :class="{ disabled: phase !== 'adding' || trait.enabled === false }" @click.stop="api.openTraitDetail(trait)">{{ api.displayName(trait.name) }}</span>
      <span v-if="trait.statement" class="sub-trait-statement">{{ trait.statement }}</span>
    </div>
    <div v-if="api.isContainer(trait)" class="sub-trait-right container-cell">
      <div v-if="api.traitDiceGroups(trait).length" class="trait-die-groups">
        <div v-for="(group, gi) in api.traitDiceGroups(trait)" :key="gi" class="trait-die-group">
          <DieIcon
            v-for="(die, i) in group"
            :key="i"
            :die="die"
            class="trait-die-icon sub-trait-die"
            :style="i ? { marginLeft: '-12px' } : null"
          />
        </div>
      </div>
      <span v-else-if="trait.ratingType !== 'EMPTY'" class="trait-die" :class="`die-${api.resolvedDieType(trait)}`">{{ api.resourceDisplay(trait) }}</span>
      <div v-if="api.hasContents(trait)" class="container-toggle">
        <Button
          variant="ghost"
          size="icon"
          :title="api.isExpanded(trait) ? 'Hide contents' : 'Show contents'"
          :aria-expanded="api.isExpanded(trait) ? 'true' : 'false'"
          :aria-controls="childrenListId"
          @click.stop="api.toggleExpand(trait)"
        >
          <span class="container-chevron" :class="{ open: api.isExpanded(trait) }">▶</span>
        </Button>
        <span class="container-count">{{ api.containerCount(trait) }}</span>
      </div>
    </div>
    <div v-else class="sub-trait-right" @click.stop="api.playTrait(trait)" :title="'Play ' + api.displayName(trait.name)">
      <div v-if="api.traitDiceGroups(trait).length" class="trait-die-groups">
        <div v-for="(group, gi) in api.traitDiceGroups(trait)" :key="gi" class="trait-die-group">
          <DieIcon
            v-for="(die, i) in group"
            :key="i"
            :die="die"
            class="trait-die-icon sub-trait-die"
            :style="i ? { marginLeft: '-12px' } : null"
          />
        </div>
      </div>
      <span v-else-if="trait.ratingType !== 'EMPTY'" class="trait-die" :class="`die-${api.resolvedDieType(trait)}`">{{ api.resourceDisplay(trait) }}</span>
    </div>
  </div>

  <!-- Children, at any depth. A traits' sub-traits are part of it, so those
       show inline as they always have; a CONTAINER stays collapsed until it is
       opened, since its children are picks in their own right. Each level nests
       its own list, so the indent accumulates on its own. A nested row's
       children render without a fog-of-war check — by the time we are here the
       root of the chain has already passed it, which is how sub-traits have
       always behaved. -->
  <div v-if="renderChildren" :id="childrenListId" class="sub-trait-list">
    <TraitRow
      v-for="child in children"
      :key="child.id"
      :trait="child"
      :api="api"
      :phase="phase"
      :depth="depth + 1"
      :inside-container="api.isContainer(trait)"
    />
  </div>
</template>

<script setup>
// A single trait-list item — the known trait row, the unknown ("???") row, and
// the traits nested under it. Presentational: every helper and every interaction
// arrives through `api` (functions only), matching the detail panel's contract.
// `wrap` is the profile view's chip layout.
//
// **Recursive.** A trait's sub-traits render through this same component with
// `depth` incremented, so nesting is limited only by what the query delivered
// (see `utils/traitTree.js`). `depth` 0 is the top-level row; anything deeper
// uses the compact sub-trait markup, and each level nests its own list so the
// indent accumulates on its own.
import { computed } from 'vue'
import DieIcon from '@/components/DieIcon.vue'
import SfxCard from './SfxCard.vue'
import Button from '@/components/ui/Button.vue'
import { childrenOf, showsChildren } from '@/utils/traitTree.js'

const props = defineProps({
  trait: { type: Object, required: true },
  api: { type: Object, required: true },
  phase: { type: String, default: '' },
  limitReached: { type: Boolean, default: false },
  wrap: { type: Boolean, default: false },
  // 0 = a row in the set's trait list; > 0 = nested under a parent. Whether the
  // row can be dragged is the sheet's call (api.canDrag), since it depends on
  // depth, on what the parent is, and on what else is on screen.
  depth: { type: Number, default: 0 },
  // True when this row sits directly under a container — the only nested rows
  // that may be picked up.
  insideContainer: { type: Boolean, default: false },
})

const children = computed(() => childrenOf(props.trait))

// Ties the toggle to the list it opens (`aria-controls`).
const childrenListId = computed(() => `children-${props.trait.id}`)

// The rendering rule lives in the model (utils/traitTree.js) so it can be
// checked without a browser: a container stays collapsed until opened, while
// everything else shows its sub-traits inline as it always has.
const renderChildren = computed(() =>
  showsChildren(props.trait, {
    rootKnown: props.depth > 0 || props.api.isKnown(props.trait),
    expanded: props.api.isExpanded(props.trait),
  })
)

// The body toggles a container open, while every other row opens its detail.
// An EMPTY container has nothing to disclose, so it opens its detail like any
// other trait rather than swallowing the tap. A container's own name always
// opens the detail either way.
function onRowClick() {
  // A drop lands on the row under the pointer, and a click follows it.
  if (props.api.clickSuppressed()) return
  if (props.api.hasContents(props.trait)) props.api.toggleExpand(props.trait)
  else props.api.openTraitDetail(props.trait)
}
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

/* The statement is the identity of *this* instance; the definition name is the
   base it derives from. So when a statement exists the emphasis flips — the
   name drops to a dim kicker and the statement carries the row. With no
   statement the name stays the prominent line, since then it is all there is. */
.trait-left.has-statement .trait-name {
  font-size: 10px;
  color: var(--text-dim);
  letter-spacing: 0.02em;
}
.trait-left.has-statement .trait-statement {
  font-size: 13px;
  color: var(--text);
}
.sub-trait-left.has-statement .sub-trait-name {
  font-size: 10px;
  color: var(--text-dim);
}
.sub-trait-left.has-statement .sub-trait-statement {
  font-size: 13px;
  opacity: 1;
  color: var(--text);
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

/* ── Container rows ──────────────────────────────────────────────────────
   A container is an ordinary trait. Its cell keeps whatever rating the instance
   has — a container *may* be rated — and adds a disclosure line below it, and
   only when there is something to disclose. An empty container therefore
   renders exactly like any other trait, which is the state it is in the moment
   it is tagged.

   The control is the shared icon `Button` (32×32 — the same target as the GM
   location tree's disclosure), so touch sizing, press feedback, focus ring and
   reduced-motion handling all come from the primitive. */
.container-cell {
  gap: 2px;
}

.container-toggle {
  display: flex;
  align-items: center;
  gap: 2px;
  color: var(--text-dim);
}

.container-chevron {
  display: inline-block;
  font-size: 11px;
  line-height: 1;
  transition: transform 0.15s;
}

.container-chevron.open {
  transform: rotate(90deg);
}

@media (prefers-reduced-motion: reduce) {
  .container-chevron { transition: none; }
}

.container-count {
  font-size: 10px;
  min-width: 10px;
  text-align: right;
  opacity: 0.8;
}

/* ── Dragging a trait into a container ───────────────────────────────────
   The grip mirrors the GM tree's handle (same 32px tall target, same hover and
   grab cursor) so the two surfaces feel alike. It is only rendered when the set
   holds a container — see `draggable`. */
.trait-drag-handle {
  width: 24px;
  min-height: 32px;
  line-height: 32px;
  text-align: center;
  flex-shrink: 0;
  user-select: none;
  color: var(--text-dim);
  cursor: grab;
  font-size: 14px;
  border-radius: 6px;
  transition: background 0.12s, color 0.12s;
}

/* A nested row is smaller, so its grip follows the row's own scale. */
.trait-drag-handle.sub-trait-grip {
  width: 20px;
  min-height: 24px;
  line-height: 24px;
  font-size: 12px;
}

.trait-drag-handle:hover {
  color: var(--text);
  background: var(--overlay-8);
}

.trait-drag-handle:active {
  cursor: grabbing;
  background: var(--overlay-12);
}

.trait-row.dragging,
.sub-trait-row.dragging {
  opacity: 0.4;
}

/* The container under the pointer — the same treatment the GM tree gives a
   valid drop target. */
.trait-row.drag-over,
.sub-trait-row.drag-over {
  background: var(--accent-16);
  box-shadow: inset 0 0 0 1px var(--accent);
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
