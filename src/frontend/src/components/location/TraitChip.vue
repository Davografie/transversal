<template>
  <div
    class="trait-chip"
    :class="{ 'scene-chip': isPlaced, draggable }"
    :style="sceneStyle"
  >
    <!-- The trait's `navdot` marker image (`B200`) — the registry trait's picture,
         when it has one. Leading the chip, so it scans picture → name → rating, the
         order the sheet's trait rows use. A cutout becomes a RING the subject rises
         out of, exactly as a cutout occupant dot composes on this map. -->
    <span
      v-if="trait.navdotImage"
      class="trait-chip-marker"
      :class="{ transparent: trait.navdotTransparent }"
    >
      <MediaImage :src="trait.navdotImage" class="trait-chip-marker-img" :alt="trait.name" />
    </span>
    <div class="trait-chip-text">
      <span class="trait-chip-name">
        <span v-if="trait.inherited" class="trait-chip-inherited" aria-hidden="true">↳</span>{{ trait.name }}
      </span>
      <span v-if="trait.statement" class="trait-chip-statement">{{ trait.statement }}</span>
    </div>
    <!-- The rating renders exactly as the sheet's trait rows do: one fanned
         staircase per die type, not a flat row. -->
    <div v-if="trait.dice && trait.dice.length" class="trait-chip-rating">
      <div class="trait-die-groups">
        <div v-for="(group, gi) in traitDiceGroups(trait)" :key="gi" class="trait-die-group">
          <DieIcon
            v-for="(die, i) in group"
            :key="i"
            :die="die"
            class="trait-die-icon"
            :style="i ? { marginLeft: FAN_X, marginTop: `${i * FAN_Y}px` } : null"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import DieIcon from '../DieIcon.vue'
import MediaImage from '../MediaImage.vue'

// A location's trait, drawn as a chip. One component for BOTH places it appears —
// the auto-stack beside the labels and, once placed, a scene element that pans with
// the map — because the two differ only in how they are positioned, and a second
// copy of this markup would drift from the first.
//
// The presentation is the sheet's ([[TraitRow]]): name on row 1, statement on row 2,
// and the rating as fanned DieIcon staircases. The chip's own height follows its
// TEXT — the dice are out of flow so they can stand taller than the chip and paint
// over its right border, which is what hides that piece of it.
const props = defineProps({
  trait: { type: Object, required: true },
  // Scene placement, in image-space percentages. Absent ⇒ the chip is unplaced and
  // the parent stacks it; present ⇒ it is absolutely placed in the scene.
  x: { type: Number, default: null },
  y: { type: Number, default: null },
  // The GM may drag it (arrange mode) — see `usePercentDrag`.
  draggable: { type: Boolean, default: false },
})

const isPlaced = computed(() => props.x !== null && props.y !== null)
const sceneStyle = computed(() => (isPlaced.value ? { left: props.x + '%', top: props.y + '%' } : null))

// Fan geometry for a group's staircase. The sheet overlaps each die onto the one
// before it by 20px and steps it down 4px, at 32×34 dice; these are the same
// proportions at this chip's 24×26 (see `.trait-die-icon`), which keeps the dice
// taller than a one-row chip so they overhang it.
const FAN_X = '-15px'
const FAN_Y = 3

// One staircase per die type, ascending d4 → d12 (`groupByDieType` in
// `CharacterSheet.vue`), so `d6 d8 d6` draws a pair of d6s and a d8. Mirrored from
// the sheet rather than imported because the sheet keeps it component-local; this
// is now the second copy, so it is the one that should move to a shared util.
function traitDiceGroups(trait) {
  const groups = []
  const byType = new Map()
  for (const d of (trait.dice || [])) {
    const die = String(d).toLowerCase()
    if (!byType.has(die)) {
      const group = []
      byType.set(die, group)
      groups.push(group)
    }
    byType.get(die).push(die)
  }
  groups.sort((a, b) => parseInt(a[0].slice(1), 10) - parseInt(b[0].slice(1), 10))
  return groups
}
</script>

<style scoped>
.trait-chip {
  position: relative;           /* the rating is absolutely placed against this */
  display: flex; align-items: center; gap: 8px;
  /* The right padding is a LANE for the dice, not part of the chip's own size: the
     height here is the text and its padding, nothing else. */
  padding: 3px 22px 3px 9px;
  border: 1px solid rgba(255,255,255,0.18);
  border-radius: 11px;          /* the ordinary chip edge, on every corner */
  background: rgba(10,10,20,0.55);
  backdrop-filter: blur(4px);
  font-size: 12px;
  text-shadow: 0 1px 6px rgba(0,0,0,0.85);
}

/* Placed: a scene element at its stored image-space x/y, centred on it, so it pans
   and zooms with the map exactly like a nav dot. Declared after the base rule so it
   wins `position` within this one stylesheet. */
.scene-chip {
  position: absolute;
  transform: translate(-50%, -50%);
  z-index: 3;
}

/* Interactive wherever it is drawn: a click plays the trait (see `useTraitPlay`), and
   in arrange mode the GM drags it instead. The containers it sits in are
   `pointer-events: none` so they never eat a map click, so the chip opts back in. */
.trait-chip { pointer-events: auto; cursor: pointer; }

.trait-chip.draggable { cursor: grab; }

.trait-chip-text { display: flex; flex-direction: column; min-width: 0; }
.trait-chip-name { color: var(--map-text); }

/* The trait's marker picture (`B200`). Between the text and the rating dice, so it
   leads the chip without competing with the dice; `flex-shrink: 0` so a long
   statement cannot squash it. `align-self: stretch` gives it the height the chip's
   TEXT set, which is what the cutout below measures itself against. */
.trait-chip-marker {
  position: relative;
  align-self: stretch;
  width: 20px;
  flex-shrink: 0;
}

/* A plain picture is a small round thumbnail, contained in the chip. */
.trait-chip-marker-img {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 20px;
  height: 20px;
  object-fit: cover;
  border-radius: 50%;
  transform: translate(-50%, -50%);
}

/* A cutout does not sit IN the chip — it stands out of it. No ring and no frame: the
   picture is absolutely placed (so the chip's height stays its text's, exactly as the
   dice are) and sized taller than the chip, measured off the text height plus a fixed
   overhang, so it breaks the chip's outline above and below whatever the chip's
   height turns out to be. Same "the art is not confined to the widget" reading as a
   cutout occupant dot on this map, without its ring. */
.trait-chip-marker.transparent .trait-chip-marker-img {
  width: auto;
  height: calc(100% + 20px);
  object-fit: contain;
  border-radius: 0;
}

.trait-chip-statement {
  color: var(--map-text-dim);
  font-size: 11px;
  font-style: italic;
  /* Two rows at most: the name is row 1, the statement row 2, and a long statement
     clips rather than wrapping the chip taller. */
  max-width: 34vw;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.trait-chip-inherited { color: var(--map-text-dim); opacity: 0.75; margin-right: 4px; }

/* Out of flow, so the chip's height stays the TEXT's and the dice may be taller than
   it. `right` is slightly negative and the z-index sits above the border: the dice
   straddle the chip's right edge and paint over it. */
.trait-chip-rating {
  position: absolute;
  right: -6px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 1;
  display: flex; align-items: center;
}

.trait-die-groups { display: flex; align-items: flex-start; gap: 8px; }
.trait-die-group { display: flex; align-items: flex-start; }

.trait-die-icon {
  /* Deliberately taller than a one-row chip (~21px), so the glyphs overhang it. */
  width: 24px;
  height: 26px;
}
</style>
