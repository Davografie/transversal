<template>
  <!-- One node per trait, holding the row AND its contents. Without this the two
       were siblings in the list, so the list's `gap` opened a seam between a
       trait and its own sub-traits — which made the sub-traits look like they
       did not belong ("the neutron staff is the asset; damaged is a detail that
       lives on the staff"). -->
  <div class="trait-node" :class="{ wrap, 'has-contents': renderChildren, 'is-morph': trait.ego === false, 'is-negative': trait.polarity === 'NEGATIVE' }">
  <!-- Whom this relationship concerns: a header for the block of traits that
       belong to it, drawn above the first of them. The sheet decides which row
       carries it (`relationGroups`), and it sits *outside* `.trait-row` on
       purpose — the row is a control (it plays the trait, it drags), and a label
       that plays a trait when you click it would be a small lie.
       The type is stated only when it is not the common `relation`: "membership"
       of Iron Roots is a different thing from a personal tie, and saying
       `relation` on every other group is noise. -->
  <div
    v-if="depth === 0 && relationHead && api.isKnown(trait)"
    class="relation-head"
    :data-contact-id="relationHead.contactId"
  >
    <span class="relation-arrow" aria-hidden="true">→</span>
    <span class="relation-contact">{{ relationHead.name }}</span>
    <span v-if="relationHead.type && relationHead.type !== 'relation'" class="relation-type">{{ relationHead.type }}</span>
  </div>
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
    <!-- The trait's picture (`B200`) — the registry definition's `sheet` role, so a
         spirit herb is a thing you can see rather than a stat line. A cutout floats
         (no frame, `contain`) exactly as the entity portrait does; an opaque
         picture keeps a rounded frame, so a list of mixed art still reads as a
         list. Leading the row, so it scans picture → name → rating. -->
    <MediaImage
      v-if="trait.sheetImage"
      :src="trait.sheetImage"
      class="trait-picture"
      :class="{ transparent: trait.imageTransparent }"
      :alt="api.displayName(trait.name)"
    />
    <div class="trait-left" :class="{ 'has-statement': !!trait.statement }">
      <span class="trait-name" :class="{ disabled: phase !== 'adding' || api.isResourceDepleted(trait) }" @click.stop="api.openTraitDetail(trait)">{{ api.displayName(trait.name) }}</span>
      <span v-if="api.traitTimerLabel(trait)" class="trait-timer" :title="'Re-enables after ' + api.traitTimerLabel(trait)">⏳ {{ api.traitTimerLabel(trait) }}</span>
      <span v-if="trait.enabled === false" class="trait-disabled-badge">disabled</span>
      <span v-if="trait.statement" class="trait-statement">{{ trait.statement }}</span>
      <div v-if="trait.sfxIds?.length || trait.grantedSfxIds?.length" class="sfx-cards">
        <SfxCard v-for="sfxId in trait.sfxIds" :key="sfxId" v-bind="api.sfxCardModel(sfxId, 'chip')"
                 @activate="api.activateSfx(sfxId, trait.id)" />
        <!-- Rules this trait simply **has** — granted to it by a rule's reach
             declaration, not attached to the instance ([[Dynamic SFX Reach]]). They
             are read-time: nothing was written on the trait, so there is nothing here
             to detach (the edit panel's list stays what is *attached*), and such a
             rule can stop applying when the world changes — a place that no longer
             qualifies, a trait that left the set. They are activatable like any other,
             so they carry the same card rather than an inert one. -->
        <SfxCard
          v-for="sfxId in (trait.grantedSfxIds || [])"
          :key="'granted-' + sfxId"
          class="sfx-granted"
          v-bind="api.sfxCardModel(sfxId, 'chip')"
          @activate="api.activateSfx(sfxId, trait.id)"
        />
      </div>
      <!-- The notes, where the host asks for them and the statement is not already
           saying the same thing in one line. A trait with a `statement` reads as
           name + statement everywhere else on the sheet, with the notes one click
           away in the detail; without a statement the notes *are* the trait's only
           prose, and hiding them hides it entirely. After the SFX cards so the row
           reads in the detail view's own order: statement → rules → notes.

           Rendered as markdown through the shared util (which escapes HTML), the
           same way the detail does — hence the `:deep()` selectors below, since
           the tags come from `v-html` and never carry this component's scope id. -->
      <div v-if="showNotes && !trait.statement && trait.notes" class="trait-notes" v-html="renderMarkdown(trait.notes)"></div>
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
      <!-- A challenge *container* keeps its track like any other challenge. It
           used to fall straight through to the plain die span, so `Portents`
           (capacity [d6,d6,d6,d8]) drew nothing and the agenda's four slots
           were invisible. -->
      <ChallengeTrack
        v-else-if="trait.ratingType === 'CHALLENGE'"
        :trait="trait"
        :api="api"
      />
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
      <ChallengeTrack
        v-else-if="trait.ratingType === 'CHALLENGE'"
        :trait="trait"
        :api="api"
      />
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
    @contextmenu.prevent="api.startEdit(trait)"
    @dragover.prevent="api.onTraitDragOver($event)"
    @dragleave="api.onTraitDragLeave()"
    @drop.prevent="api.onTraitDrop($event)"
    @dragend="api.onTraitDragEnd()"
  >
    <!-- The author's position in an ordered container's sequence, and it leads
         the row. The lane renders for every child of one, including a child with
         no `order`, so the names stay on one column — which is the whole point:
         without it the rows are a bag again, just stacked. Leading, rather than
         sitting after the grip, because a row's grip depends on where *that* row
         may be dropped: a child that is itself a container can have fewer
         destinations than its siblings, and the numbers would then step in and
         out of line. -->
    <span v-if="ordered" class="sub-trait-order">{{ trait.order ?? '' }}</span>
    <!-- A row inside a container carries a grip, at ANY depth, so it can be
         pulled back OUT. Dropping it on any non-container row does that (see the
         sheet's resolveTarget), which lands it at the top of the set. A sub-trait
         of a NON-container gets none at any depth: it is part of its parent. -->
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
      <span v-if="trait.enabled === false" class="trait-disabled-badge">disabled</span>
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
      <ChallengeTrack
        v-else-if="trait.ratingType === 'CHALLENGE'"
        :trait="trait"
        :api="api"
        compact
      />
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
      <!-- A nested challenge is a portent: a one-slot track waiting to be filled.
           Without this branch it fell to the plain die span and drew nothing, so
           the very sub-trait the ticket is about showed no state at all. -->
      <ChallengeTrack
        v-else-if="trait.ratingType === 'CHALLENGE'"
        :trait="trait"
        :api="api"
        compact
      />
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
  <div v-if="renderChildren" :id="childrenListId" class="sub-trait-list" :class="{ ordered: orderedContents }">
    <TraitRow
      v-for="child in children"
      :key="child.id"
      :trait="child"
      :api="api"
      :phase="phase"
      :depth="depth + 1"
      :inside-container="api.isContainer(trait)"
      :ordered="orderedContents"
    />
  </div>
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
import MediaImage from '@/components/MediaImage.vue'
import SfxCard from './SfxCard.vue'
import ChallengeTrack from './ChallengeTrack.vue'
import Button from '@/components/ui/Button.vue'
import { isOrdered, orderedChildren, showsChildren } from '@/utils/traitTree.js'
import { renderMarkdown } from '@/utils/markdown.js'

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
  // The head of a run of rows about one relationship — `{ name, type, contactId }`
  // from `relationGroups`, or null when this row does not start one. The row that
  // carries it draws the block's header.
  relationHead: { type: Object, default: null },
  // This row sits in an **ordered** container, so it carries a leading marker
  // lane with its own `order` (see `ORDERED_TAG` in utils/traitTree.js). The
  // lane renders for every child of such a container — including one with no
  // `order` — so the numbers and the names line up on one column.
  ordered: { type: Boolean, default: false },
  // Show a trait's full notes inline when it has no `statement`. The host's call,
  // because the answer differs by list: on the profile page a described trait with
  // nothing else to say would otherwise render as a bare name, while the traits
  // tab is a dense list of lines where a paragraph per trait is a different
  // question. Default `false` so only a list that asks for it gets it.
  showNotes: { type: Boolean, default: false },
})

const children = computed(() => orderedChildren(props.trait))

// Whether this trait's contents are an authored sequence rather than a bag —
// the author's `ordered` tag on the container, not an inference from `order`.
const orderedContents = computed(() => isOrdered(props.trait))

// Ties the toggle to the list it opens (`aria-controls`).
const childrenListId = computed(() => `children-${props.trait.id}`)

// The rendering rule lives in the model (utils/traitTree.js) so it can be
// checked without a browser: a container stays collapsed until opened, while
// everything else shows its sub-traits inline as it always has. A trait inside a
// container renders without its own sub-traits — those are part of it — *except*
// a container nested inside a container, whose disclosure would otherwise open
// nothing (see showsChildren).
const renderChildren = computed(() =>
  showsChildren(props.trait, {
    rootKnown: props.depth > 0 || props.api.isKnown(props.trait),
    expanded: props.api.isExpanded(props.trait),
    insideContainer: props.insideContainer,
  })
)

// A container shows its contents as an inline, wrapping row rather than a
// stacked list of rows.

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
  /* The tint is on the node now (see .trait-node.is-morph) so it can wrap the
     trait's contents too; painting it here as well would double it. */
  background: transparent;
  border-left: none;
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

/* Whom a relationship concerns, heading the block of its traits. Quiet and
   full-width, with a rule above it: it is a label for the rows under it, not a
   row itself, and the rule is what makes a stack of relationships read as a
   stack rather than as one long list of traits. */
.relation-head {
  display: flex;
  align-items: baseline;
  gap: 4px;
  padding: 2px 2px 1px;
  border-top: 1px solid var(--overlay-8);
  font-size: 11px;
  color: var(--text);
}
.relation-head .relation-arrow { color: var(--accent); font-size: 10px; }
.relation-head .relation-contact { font-weight: 600; }
.relation-head .relation-type {
  font-size: 9px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.5px;
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

/* The trait's picture (`B200`). Sized to the row's first text line rather than
   the row: a described trait is several lines tall and the picture belongs with
   the name, not floating in the middle of the prose. `flex-shrink: 0` so a long
   statement cannot squash it. */
.trait-picture {
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  margin-top: 1px;
  border-radius: 4px;
  border: 1px solid var(--overlay-12);
  object-fit: cover;
}
/* A cutout carries its own shape, so it gets no frame and no crop. */
.trait-picture.transparent {
  border: none;
  border-radius: 0;
  object-fit: contain;
}

/* A trait's notes, shown inline where the host asks for them and there is no
   statement to carry the row (see the `showNotes` prop). Body text, not a
   caption: this is the trait's whole description, so it reads at the sheet's
   normal size rather than the statement's small italic. `max-width: 100%` keeps
   it inside the profile page's wrapping chip row.
   `:deep()` is required — the markdown tags come from `v-html` and never carry
   this component's scope attribute, so a plain `.trait-notes p { … }` would
   compile to `.trait-notes p[data-v-x]` and match nothing. (BlueBook has exactly
   that bug; the detail panel documents it too.) */
.trait-notes {
  max-width: 100%;
  font-size: 12px;
  line-height: 1.45;
  color: var(--text);
  word-wrap: break-word;
}
.trait-notes :deep(p) { margin: 2px 0; }
.trait-notes :deep(p:first-child) { margin-top: 0; }
.trait-notes :deep(p:last-child) { margin-bottom: 0; }
.trait-notes :deep(ul),
.trait-notes :deep(ol) { margin: 2px 0; padding-left: 18px; }
.trait-notes :deep(li) { margin: 1px 0; }
.trait-notes :deep(a) { color: var(--accent); text-decoration: underline; }
.trait-notes :deep(strong) { font-weight: 700; }
.trait-notes :deep(em) { font-style: italic; }
.trait-notes :deep(code) {
  font-family: monospace;
  font-size: 11px;
  background: var(--overlay-8);
  padding: 1px 4px;
  border-radius: 3px;
}
.trait-notes :deep(blockquote) {
  border-left: 3px solid var(--accent);
  margin: 4px 0;
  padding: 2px 10px;
  color: var(--text-dim);
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

/* One node per trait, holding the row AND its contents. Their being siblings in
   the list is what used to open a seam between a trait and its own sub-traits —
   which made the sub-traits read as unrelated ("the neutron staff is the asset;
   damaged is a detail that lives on the staff"). */
.trait-node {
  display: flex;
  flex-direction: column;
}

.trait-node.has-contents {
  background: var(--overlay-2);
  border-radius: 8px;
  padding: 2px 3px 3px;
}

/* In the profile's chip layout the NODE is the flex item, so the node is what
   grows to fill the line. */
.trait-node.wrap {
  flex: 1 1 auto;
  max-width: 100%;
}

/* The morph tint belongs to the whole trait, not just its header: a body's
   details are as much the body's as the trait is. So it lives on the node,
   which holds the row AND its contents. Placed after `has-contents` so it wins
   that tie — a morph container is tinted, not neutral. */
.trait-node.is-morph {
  background: var(--accent-8);
  border-left: 2px solid var(--accent);
  border-radius: 8px;
}

.trait-node.is-morph.is-negative {
  background: color-mix(in srgb, var(--die-d8-neg) 14%, transparent);
  border-left-color: var(--die-d8-neg);
}

/* Sub-traits — and a container's contents — are small chips that wrap in-line.
   They pack to the RIGHT rather than stretching: the right edge is where the
   trait's own die sits, so they read as hanging off it. (That is what the old
   app did — `justify-content: end` — and the human asked for it back; the
   profile chips still stretch, since there the node is the flex item.) */
.sub-trait-list {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 4px;
  padding: 4px 2px 2px 12px;
}

/* An **ordered** container's contents are a sequence, so they stack instead of
   packing as chips. The chip layout is right-packed, which is right for a bag
   and wrong for a list: a narrow first step then sits further right than the
   steps after it (measured on the live portents: first entry x=361, the rest
   x=292), and a wrapped line reads in no particular direction. */
.sub-trait-list.ordered {
  flex-direction: column;
  align-items: stretch;
  justify-content: flex-start;
  gap: 2px;
}

/* The number lane. `tabular-nums` and a fixed min-width so `1` and `10` centre
   on the same column, and it stays open for a child with no `order` — the lane
   is what keeps the names aligned, not the numbers themselves.
   Pinned to the row's first line rather than its centre: on a described trait
   the statement is the tall line, and a number floating between the name and the
   statement belongs to neither. */
.sub-trait-order {
  flex-shrink: 0;
  min-width: 14px;
  align-self: flex-start;
  padding-top: 1px;
  text-align: right;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--text-dim);
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
  /* A chip, sized to its content so the row can be packed right. */
  flex: 0 0 auto;
  max-width: 100%;
  background: var(--overlay-4);
}

.sub-trait-row:hover {
  background: var(--overlay-8);
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

/* Both left columns are `flex-direction: column`, whose default `align-items:
   stretch` would make a pill span the column instead of hugging its own word.
   Scoped here rather than in the shared `.trait-disabled-badge`: in the detail
   panel's header the badge sits in a *row*, where stretching is meaningless. */
.trait-left .trait-disabled-badge,
.sub-trait-left .trait-disabled-badge {
  align-self: flex-start;
}

.sub-trait-statement {
  font-size: 11px;
  opacity: 0.75;
}

/* The granted card's dashed edge is a shared treatment now — see `.sfx-granted` in
   assets/styles.css, where it lives so the sheet's entity, projection and trait-set
   strips cannot drift from this row. */
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
  /* Likewise: the node carries the negative-morph tint, so the row only keeps
     its die colours (set above). */
  background: transparent;
  border-left: none;
}
</style>
