<template>
  <!-- Embedded: single root for attribute inheritance -->
  <div v-if="embedded" class="sheet-embedded" :class="{ 'transparent-portrait': sheetPortraitTransparent }">
    <div v-if="loading" class="loading">Loading…</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <template v-else-if="entity">
      <div class="header">
        <div class="header-top">
          <div class="header-title">
            <!-- A named body takes over the title; the character's name shrinks
                 to an overline above it. Unnamed: the character keeps the title
                 and the naming action sits underneath. The edit input always
                 swaps into the slot of the level it edits, so the header
                 doesn't reflow when you click. -->
            <div v-if="projectionSubtitle" class="name-overline">{{ entity.name }}</div>

            <template v-if="projectionSubtitle">
              <input
                v-if="editingProjectionName"
                ref="projectionNameInput"
                v-model="projectionNameValue"
                class="projection-name-input is-primary"
                placeholder="Name this projection…"
                @keyup.enter="commitProjectionName"
                @keyup.escape="editingProjectionName = false"
                @blur="commitProjectionName"
              />
              <h2 v-else class="name-primary">
                <Button
                  v-if="canEditProjectionName"
                  variant="link"
                  class="name-primary-btn"
                  title="Rename this projection"
                  @click.stop="startProjectionNameEdit"
                >{{ projectionSubtitle }}</Button>
                <span v-else>{{ projectionSubtitle }}</span>
              </h2>
            </template>

            <template v-else>
              <h2 class="name-primary">{{ entity.name }}</h2>
              <div v-if="canEditProjectionName" class="name-secondary">
                <input
                  v-if="editingProjectionName"
                  ref="projectionNameInput"
                  v-model="projectionNameValue"
                  class="projection-name-input"
                  placeholder="Name this projection…"
                  @keyup.enter="commitProjectionName"
                  @keyup.escape="editingProjectionName = false"
                  @blur="commitProjectionName"
                />
                <Button
                  v-else
                  variant="link"
                  class="projection-name-btn unset"
                  title="Name this projection"
                  @click.stop="startProjectionNameEdit"
                >＋ Name this projection</Button>
              </div>
            </template>
          </div>
          <div class="razmerit-anchor">
            <button class="razmerit-chip" :title="showRazmeritWidget ? 'Close' : 'Adjust razmerit'" @click.stop="showRazmeritWidget = !showRazmeritWidget">
              ⚡{{ entity.razmerit }}
            </button>
            <div v-if="showRazmeritWidget" class="razmerit-popover" @click.stop>
              <Button v-if="!overrideEntityId" variant="ghost" size="icon" title="Decrease razmerit" @click.stop="adjustRazmerit(-1)">−</Button>
              <input
                v-if="editingRazmerit"
                ref="razmeritInput"
                v-model="razmeritInputValue"
                class="razmerit-input"
                type="number"
                inputmode="numeric"
                @keyup.enter="commitRazmerit"
                @keyup.escape="editingRazmerit = false"
                @blur="commitRazmerit"
              />
              <span
                v-else
                class="razmerit-value"
                :class="{ editable: !overrideEntityId }"
                @click="!overrideEntityId && startRazmeritEdit()"
              >{{ entity.razmerit }}</span>
              <Button v-if="!overrideEntityId" variant="ghost" size="icon" title="Increase razmerit" @click.stop="adjustRazmerit(1)">+</Button>
            </div>
          </div>
          <MediaImage v-if="sheetPortrait" :src="sheetPortrait" class="sheet-portrait" :class="{ transparent: sheetPortraitTransparent }" />
        </div>
        <div class="header-controls">
          <div v-if="isForeignSheet" class="rel-widget">
            <template v-if="relationship">
              <span class="rel-desc" @click.stop="showRelEditor = true" :title="'Click to edit'">{{ relationship.description || 'related' }}</span>
              <Button variant="danger-ghost" size="sm" title="Remove relationship" @click.stop="removeRelationship">✕</Button>
              <Button variant="ghost" size="icon" title="Send letter" @click.stop="openBlueBookLetter">✉</Button>
            </template>
            <div v-if="showRelEditor" class="rel-editor" @click.stop>
              <input ref="relInput" v-model="relDescription" placeholder="Describe relationship…" @keyup.enter="saveRelationship" @keyup.escape="showRelEditor = false" />
              <Button variant="primary" size="icon" title="Save relationship" @click="saveRelationship">✓</Button>
              <Button variant="ghost" size="icon" title="Cancel" @click="showRelEditor = false">✕</Button>
            </div>
          </div>
          <div class="sheet-pills">
            <div v-if="gmMode || !overrideEntityId || showRelationTab">
              <button
                v-if="showRelationTab"
                :class="['pill', { active: activeSheetView === 'relation' }]"
                :title="`What you hold about ${entity.name}`"
                @click="activeSheetView = 'relation'"
              >🤝</button>
              <template v-if="gmMode || !overrideEntityId">
                <button :class="['pill', { active: activeSheetView === 'profile' }]" @click="activeSheetView = 'profile'">👤</button>
                <button :class="['pill', { active: activeSheetView === 'traits' }]" @click="goToTraitSets">🎲</button>
                <button v-if="gmMode" :class="['pill', { active: showAllTraits }]" :title="showAllTraits ? 'Showing all traits' : 'Show all traits'" @click="showAllTraits = !showAllTraits">🌍</button>
                <button :class="['pill', { active: activeSheetView === 'bluebook' }]" @click="activeSheetView = 'bluebook'">📘</button>
                <button :class="['pill', { active: activeSheetView === 'lifepath' }]" @click="activeSheetView = 'lifepath'">🛤️</button>
              </template>
            </div>
            <Button v-if="!gmMode && !isForeignSheet" variant="ghost" size="icon" title="Player settings" @click.stop="$emit('openSettings')">↩</Button>
            <Button v-if="isForeignSheet && !relationship" variant="ghost" size="icon" title="Add relationship" @click.stop="createImmediateRelationship()">+</Button>
          </div>
        </div>
        <div v-if="entitySfxIds.length || projectionSfxIds.length" class="entity-sfx-cards">
          <div v-for="sfxId in entitySfxIds" :key="'e-' + sfxId" class="sfx-card"
               :class="{ 'sfx-active': sfxActive(sfxId), 'sfx-used': sfxUsed(sfxId) && !sfxActive(sfxId), 'sfx-blocked': sfxConditionBlocked(sfxId) }"
               :title="sfxTitle(sfxId)"
               @click.stop.prevent="sfxAllowedInPhase(sfxId) && !sfxConditionBlocked(sfxId) && activateSfx(sfxId, entity.id)">
            <span class="sfx-card-name">{{ sfxName(sfxId) }}</span>
            <span v-if="sfxDescription(sfxId)" class="sfx-card-desc">{{ sfxDescription(sfxId) }}</span>
          </div>
          <div v-for="sfxId in projectionSfxIds" :key="'p-' + sfxId" class="sfx-card"
               :class="{ 'sfx-active': sfxActive(sfxId), 'sfx-used': sfxUsed(sfxId) && !sfxActive(sfxId), 'sfx-blocked': sfxConditionBlocked(sfxId) }"
               :title="sfxTitle(sfxId)"
               @click.stop.prevent="sfxAllowedInPhase(sfxId) && !sfxConditionBlocked(sfxId) && activateSfx(sfxId, activeProjection.id)">
            <span class="sfx-card-name">{{ sfxName(sfxId) }}</span>
            <span v-if="sfxDescription(sfxId)" class="sfx-card-desc">{{ sfxDescription(sfxId) }}</span>
          </div>
        </div>
        <div v-if="gmMode" class="meta">
          <span class="location">{{ locationName || entity.currentLocation || 'Unknown' }}</span>
          <span class="universe">{{ universeName || entity.currentUniverse }}</span>
          <span v-if="entityTimerLabel" class="active-effects" :title="'Timed effects pending: ' + entityTimerLabel">⏳ {{ entityTimerLabel }}</span>
        </div>
      </div>
      <BlueBook
        v-if="activeSheetView === 'bluebook'"
        :entity-id="overrideEntityId || entityId"
        ref="blueBookRef"
        :entity-name="entity?.name || ''"
        :viewer-id="viewerEntityId || entityId"
        :visible="true"
        embedded
      />
      <LifePathWizard
        v-else-if="activeSheetView === 'lifepath'"
        :visible="activeSheetView === 'lifepath'"
        :entity-id="overrideEntityId || entityId"
        :universe="entity?.currentUniverse || 'earth'"
        embedded
        @close="activeSheetView = 'traits'"
        @updated="fetchEntity"
      />
      <template v-else>
        <div class="sheet-scroll">
        <!-- Full-panel trait edit -->
        <div v-if="editingTrait && !showAddTrait" class="trait-edit-panel">
          <Button class="set-back" variant="link" @click="cancelEdit">← Back</Button>
          <h4 class="edit-title">{{ displayName(editingTrait.name) }}</h4>

          <div class="edit-field">
            <span class="edit-label">Rating</span>
            <div class="edit-rating-type">
              <button
                v-for="rt in RATING_TYPES"
                :key="rt.id"
                type="button"
                class="rating-type-btn"
                :class="{ active: editRatingType === rt.id }"
                @click="setRatingType(rt.id)"
              >{{ rt.label }}</button>
            </div>
          </div>

          <div v-if="editRatingType !== 'EMPTY'" class="edit-field">
            <span class="edit-label">Dice</span>
            <div class="edit-dice">
              <button v-for="(d, i) in editDice" :key="i" class="die-chip die-chip-icon" :title="`Change ${d}`" @click="pickIdx = i; showDiePicker = true">
                <DieIcon :die="d" />
              </button>
              <button class="die-chip add-chip" @click="pickIdx = editDice.length; showDiePicker = true">+</button>
            </div>
            <div v-if="editRatingType === 'RESOURCE' && (editingTrait.spentDice || []).length" class="edit-spent-dice">
              <span class="edit-spent-label">Recoverable</span>
              <button
                v-for="(die, i) in editingTrait.spentDice"
                :key="'spent' + i"
                class="die-chip ghost-chip die-chip-icon"
                :title="`Recover one ${die.toLowerCase()}`"
                @click="recoverSpentDie(die)"
              ><DieIcon :die="die.toLowerCase()" /></button>
            </div>
          </div>

          <div v-if="editRatingType === 'CHALLENGE'" class="edit-field">
            <span class="edit-label">Capacity</span>
            <div class="edit-dice">
              <button v-for="(d, i) in editCapacity" :key="'cap' + i" class="die-chip die-chip-icon" :title="`Change ${d}`" @click="capacityPickIdx = i; showCapacityPicker = true">
                <DieIcon :die="d" />
              </button>
              <button class="die-chip add-chip" @click="capacityPickIdx = editCapacity.length; showCapacityPicker = true">+</button>
            </div>
          </div>

          <DiePicker v-if="showDiePicker" v-model="pickedDie" @update:model-value="onDiePicked" />
          <DiePicker v-if="showCapacityPicker" v-model="pickedCapacityDie" @update:model-value="onCapacityPicked" />

          <div v-if="editingTrait.possibleSfxIds?.length" class="edit-field">
            <span class="edit-label">SFX</span>
            <div class="edit-sfx">
              <button v-for="sfxId in editingTrait.possibleSfxIds" :key="sfxId" class="sfx-chip" :class="{ assigned: editSfxIds.includes(sfxId) }" @click="toggleSfx(sfxId)">
                {{ sfxId.replace('sfx-', '') }}
              </button>
            </div>
          </div>

          <div v-if="editingTrait.statement !== undefined" class="edit-field">
            <span class="edit-label">Statement</span>
            <input v-model="editStatement" class="edit-statement" placeholder="Statement…" @input="onStatementInput" @blur="splitStatement" />
          </div>

          <div v-if="editingTrait.notes !== undefined || editNotes" class="edit-field">
            <span class="edit-label">Notes</span>
            <textarea v-model="editNotes" class="edit-notes" placeholder="Notes…" @input="onStatementInput"></textarea>
          </div>

          <div class="edit-field">
            <span class="edit-label">Type</span>
            <div class="edit-flags">
              <button v-if="editingTrait.fromType !== 'relationship'" type="button" class="ego-toggle" :class="{ 'is-ego': editIsEgo }" @click="toggleEgo">{{ editIsEgo ? 'ego' : 'morph' }}</button>
              <button type="button" class="polarity-toggle" :class="{ 'is-positive': editPolarity === 'POSITIVE' }" @click="togglePolarity">
                {{ editPolarity === 'POSITIVE' ? 'positive' : 'negative' }}
              </button>
            </div>
            <div v-if="!editIsEgo && editingTrait.fromType !== 'relationship'" class="edit-projection">
              <span class="edit-projection-label">on</span>
              <button type="button" class="projection-chip" @click="toggleProjectionPicker">{{ editProjectionName }}</button>
              <div v-if="showProjectionPicker" class="projection-dropdown">
                <button
                  v-for="p in editProjectionOptions"
                  :key="p.id"
                  type="button"
                  class="projection-option"
                  :class="{ selected: p.id === editProjectionId }"
                  @click="selectProjection(p)"
                >{{ p.name || universeDisplay(p.originUniverse) }}</button>
              </div>
            </div>
          </div>

          <div class="edit-field">
            <span class="edit-label">Sub-traits</span>
            <div v-if="(editingTrait.subTraitSettings || []).length" class="edit-subtraits">
              <div v-for="st in editingTrait.subTraitSettings" :key="st.id" class="edit-subtrait-row">
                <span class="edit-subtrait-name">{{ displayName(st.name) }}</span>
                <span v-if="st.statement" class="edit-subtrait-statement">{{ st.statement }}</span>
                <Button class="edit-subtrait-remove" variant="danger-ghost" size="sm" title="Remove sub-trait" @click="removeSubTrait(st.id)">✕</Button>
              </div>
            </div>
            <div v-if="availableSubtraits.length" class="edit-subtraits-add">
              <span class="edit-subtrait-add-label">Add:</span>
              <button v-for="opt in availableSubtraits" :key="opt.id" class="edit-subtrait-chip" @click="addSubTrait(opt.id)">{{ opt.name }}</button>
            </div>
            <span v-else-if="!(editingTrait.possibleSubtraitIds || []).length" class="edit-subtrait-empty">No sub-traits configured for this trait.</span>
          </div>

          <div class="edit-actions">
            <Button class="edit-done-btn" variant="primary" @click="cancelEdit">Done</Button>
            <Button
              class="edit-delete-btn"
              variant="danger"
              :active="deleteCountdown > 0 && deletingTraitId === editingTrait.id"
              @click="onDeleteClick(editingTrait)"
            >
              {{ deleteCountdown > 0 && deletingTraitId === editingTrait.id ? `Cancel (${deleteCountdown})` : 'Delete' }}
            </Button>
          </div>
        </div>

        <!-- Trait detail (read-only) — the row's "elsewhere" click zone.
             Right-click on the row, or the header's Edit, opens the editor. -->
        <div v-else-if="detailTrait && !showAddTrait" class="trait-detail-panel">
          <div class="detail-header">
            <Button class="detail-back" variant="link" @click="closeTraitDetail">← {{ detailTrait.traitsetName || 'Back' }}</Button>
            <Button class="detail-edit" variant="link" @click="startEdit(detailTrait)">✎ Edit</Button>
          </div>

          <div class="detail-hero">
            <div class="detail-hero-line">
              <h3 class="detail-name">{{ displayName(detailTrait.name) }}</h3>
              <span class="detail-polarity" :class="{ negative: detailTrait.polarity === 'NEGATIVE' }">● {{ detailTrait.polarity === 'NEGATIVE' ? 'negative' : 'positive' }}</span>
            </div>
            <div class="detail-kicker">
              <span v-if="detailTrait.traitsetName">{{ detailTrait.traitsetName }}</span>
              <span v-if="detailTrait.traitsetName" class="detail-kicker-sep">·</span>
              <span>{{ detailTrait.ego === false ? 'morph' : 'ego' }}</span>
              <span v-if="detailTrait.enabled === false" class="trait-disabled-badge">disabled</span>
            </div>
            <div v-if="detailTrait.tags?.length" class="detail-tags">
              <span v-for="tag in detailTrait.tags" :key="tag" class="detail-tag">{{ tag }}</span>
            </div>
          </div>

          <div
            class="detail-section detail-rating-band"
            :class="{ playable: canPlayTrait(detailTrait) }"
            :title="canPlayTrait(detailTrait) ? 'Play this trait' : ''"
            @click.stop="canPlayTrait(detailTrait) && playTrait(detailTrait)"
          >
            <div class="detail-section-head">
              <span class="detail-label">Rating</span>
              <span class="detail-meta">{{ ratingTypeLabel(detailTrait) }}</span>
            </div>
            <div class="detail-dice">
              <DieIcon v-for="(die, i) in (detailTrait.dice || [])" :key="i" :die="String(die).toLowerCase()" class="detail-die" />
              <span v-if="challengeProgressLabel(detailTrait)" class="challenge-progress">{{ challengeProgressLabel(detailTrait) }}</span>
              <span v-if="!(detailTrait.dice || []).length" class="trait-die depleted">unrated</span>
            </div>
            <div v-if="!(detailTrait.dice || []).length" class="trait-die depleted">unrated</div>
            <p v-if="detailTrait.statement" class="detail-statement">{{ detailTrait.statement }}</p>
          </div>

          <div v-if="detailTrait.sfxIds?.length" class="detail-section">
            <div class="detail-section-head"><span class="detail-label">SFX</span></div>
            <div class="sfx-cards">
              <div
                v-for="sfxId in detailTrait.sfxIds"
                :key="sfxId"
                class="sfx-card"
                :class="{ 'sfx-active': sfxActive(sfxId), 'sfx-used': sfxUsed(sfxId) && !sfxActive(sfxId), 'sfx-blocked': sfxConditionBlocked(sfxId) }"
                :title="sfxTitle(sfxId)"
                @click.stop.prevent="sfxAllowedInPhase(sfxId) && !sfxConditionBlocked(sfxId) && activateSfx(sfxId, detailTrait.id)"
              >
                <span class="sfx-card-name">{{ sfxName(sfxId) }}</span>
                <span v-if="sfxDescription(sfxId)" class="sfx-card-desc">{{ sfxDescription(sfxId) }}</span>
                <span v-if="sfxCardText(sfxId)" class="sfx-card-rules">{{ sfxCardText(sfxId) }}</span>
              </div>
            </div>
          </div>

          <div v-if="detailTrait.notes" class="detail-section">
            <div class="detail-section-head"><span class="detail-label">Notes</span></div>
            <p class="detail-text">{{ detailTrait.notes }}</p>
          </div>

          <div v-if="(detailTrait.subTraitSettings || []).length" class="detail-section">
            <div class="detail-section-head"><span class="detail-label">Sub-traits</span></div>
            <div class="detail-subtraits">
              <div v-for="st in detailTrait.subTraitSettings" :key="st.id" class="detail-subtrait">
                <span class="detail-subtrait-dice">
                  <DieIcon v-for="(die, i) in (st.dice || [])" :key="i" :die="String(die).toLowerCase()" class="detail-die-sm" />
                </span>
                <span class="detail-subtrait-name">{{ displayName(st.name) }}</span>
                <Button v-if="canPlayTrait(st)" class="detail-subtrait-play" variant="link" @click.stop="playTrait(st)">▸ play</Button>
              </div>
            </div>
          </div>

          <div v-if="detailContext(detailTrait).length" class="detail-section detail-context">
            <div v-for="row in detailContext(detailTrait)" :key="row.label" class="detail-context-row">
              <span class="detail-context-label">{{ row.label }}</span>
              <span class="detail-context-value">{{ row.value }}</span>
            </div>
          </div>
        </div>

        <!-- Traits tab: trait-set list -->
        <div v-else-if="activeSheetView === 'traits' && !activeSetName && traitSets.length && !showAddTrait" class="trait-sets">
          <div v-for="ts in traitSets" :key="ts.name" class="trait-set">
            <h4 @click="openSet(ts.name)" class="set-header">
              <span class="set-name">{{ ts.name }}</span>
              <span v-if="ts.limit" class="limit-dots">
                <span v-for="i in ts.limit" :key="i" class="limit-dot" :class="{ filled: i <= inPoolCount(ts) }">{{ i <= inPoolCount(ts) ? '●' : '○' }}</span>
              </span>
            </h4>
            <div v-if="traitsetSfxIds(ts).length" class="sfx-cards">
              <div v-for="sfxId in traitsetSfxIds(ts)" :key="'ts-' + sfxId" class="sfx-card"
                   :class="{ 'sfx-active': sfxActive(sfxId), 'sfx-used': sfxUsed(sfxId) && !sfxActive(sfxId), 'sfx-blocked': sfxConditionBlocked(sfxId) }"
                   :title="sfxTitle(sfxId)"
                   @click.stop.prevent="sfxAllowedInPhase(sfxId) && !sfxConditionBlocked(sfxId) && activateSfx(sfxId, traitsetSettingSourceId(ts))"
              >
                <span class="sfx-card-name">{{ sfxName(sfxId) }}</span>
                <span v-if="sfxDescription(sfxId)" class="sfx-card-desc">{{ sfxDescription(sfxId) }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Set detail (traits) or profile: flat trait list -->
        <div v-else-if="currentTraits.length && !showAddTrait" class="trait-list" :class="{ 'trait-list-wrap': activeSheetView === 'profile' }">
          <h4 v-if="activeSheetView === 'traits'" class="trait-list-title" @click="closeSet" title="Back to trait sets">← {{ activeSetName }}</h4>
            <template v-for="t in currentTraits" :key="t.id">
              <div v-if="isKnown(t)" class="trait-row" :class="{ morph: t.ego === false, 'in-pool': isInPool(t), offered: isOffered(t), 'limit-reached': currentSetReachedLimit && !isInPool(t), negative: t.polarity === 'NEGATIVE', 'trait-disabled': t.enabled === false }" @click="openTraitDetail(t)" @contextmenu.prevent="startEdit(t)" @touchstart="onTouchStart(t)" @touchend="onTouchEnd" @touchmove="onTouchEnd">
                <div class="trait-left">
                  <span class="trait-name" :class="{ disabled: phase !== 'adding' || isResourceDepleted(t) }">{{ displayName(t.name) }}</span>
                  <span v-if="traitTimerLabel(t)" class="trait-timer" :title="'Re-enables after ' + traitTimerLabel(t)">⏳ {{ traitTimerLabel(t) }}</span>
                  <span v-if="t.enabled === false" class="trait-disabled-badge">disabled</span>
                  <span v-if="t.fromType === 'relationship' && t.relationshipContactName" class="trait-contact">→ {{ t.relationshipContactName }}</span>
                  <span v-if="t.statement" class="trait-statement">{{ t.statement }}</span>
                  <span v-if="t.notes" class="trait-notes">{{ t.notes }}</span>
                  <div v-if="t.sfxIds?.length" class="sfx-cards">
                    <div
                      v-for="sfxId in t.sfxIds"
                      :key="sfxId"
                      class="sfx-card"
                      :class="{ 'sfx-active': sfxActive(sfxId), 'sfx-used': sfxUsed(sfxId) && !sfxActive(sfxId), 'sfx-blocked': sfxConditionBlocked(sfxId) }"
                      :title="sfxTitle(sfxId)"
                      @click.stop.prevent="sfxAllowedInPhase(sfxId) && !sfxConditionBlocked(sfxId) && activateSfx(sfxId, t.id)"
                    >
                      <span class="sfx-card-name">{{ sfxName(sfxId) }}</span>
                      <span v-if="sfxDescription(sfxId)" class="sfx-card-desc">{{ sfxDescription(sfxId) }}</span>
                    </div>
                  </div>
                </div>
                <div class="trait-right" @click.stop="playTrait(t)" :title="'Play ' + displayName(t.name)">
                  <div v-if="traitDiceGroups(t).length" class="trait-die-groups">
                    <div v-for="(group, gi) in traitDiceGroups(t)" :key="gi" class="trait-die-group">
                      <DieIcon
                        v-for="(die, i) in group"
                        :key="i"
                        :die="die"
                        class="trait-die-icon"
                        :style="i ? { marginLeft: '-20px', marginTop: `${i * 4}px` } : null"
                      />
                    </div>
                  </div>
                  <div v-else-if="t.ratingType === 'RESOURCE'" class="trait-die-groups resource">
                    <div
                      v-for="(group, gi) in resourceDiceGroups(t)"
                      :key="'a' + gi"
                      class="trait-die-group clickable"
                      :title="`Add ${group[0]} to pool`"
                      @click.stop="spendResourceGroup(t, group[0])"
                    >
                      <DieIcon
                        v-for="(die, i) in group"
                        :key="i"
                        :die="die"
                        class="trait-die-icon"
                        :style="i ? { marginLeft: '-20px', marginTop: `${i * 4}px` } : null"
                      />
                    </div>
                    <div v-for="(group, gi) in resourceSpentGroups(t)" :key="'s' + gi" class="trait-die-group">
                      <DieIcon
                        v-for="(die, i) in group"
                        :key="i"
                        :die="die"
                        class="trait-die-icon ghost"
                        :style="i ? { marginLeft: '-20px', marginTop: `${i * 4}px` } : null"
                      />
                    </div>
                    <span v-if="!(t.dice || []).length && !(t.spentDice || []).length" class="trait-die depleted">depleted</span>
                  </div>
                  <div v-else-if="t.ratingType === 'CHALLENGE'" class="trait-die-groups challenge">
                    <div
                      v-for="(group, gi) in resourceDiceGroups(t)"
                      :key="'c' + gi"
                      class="trait-die-group clickable"
                      :title="`Spend ${group[0]} from challenge pool`"
                      @click.stop="spendChallengeGroup(t, group[0])"
                    >
                      <DieIcon
                        v-for="(die, i) in group"
                        :key="i"
                        :die="die"
                        class="trait-die-icon"
                        :style="i ? { marginLeft: '-20px', marginTop: `${i * 4}px` } : null"
                      />
                    </div>
                    <span v-if="challengeProgressLabel(t)" class="challenge-progress">{{ challengeProgressLabel(t) }}</span>
                    <span v-if="!(t.dice || []).length" class="trait-die depleted">empty</span>
                  </div>
                  <span v-else class="trait-die" :class="`die-${resolvedDieType(t)}`">{{ resourceDisplay(t) }}</span>
                </div>
              </div>
              <div v-else class="trait-row unknown-trait">
                <div class="trait-left">
                  <span class="trait-name unknown">???</span>
                </div>
                <div class="trait-right">
                  <span class="trait-die unknown-die">?</span>
                </div>
              </div>
              <div v-if="isKnown(t) && (t.subTraitSettings || []).length" class="sub-trait-list">
                <div
                  v-for="st in t.subTraitSettings"
                  :key="st.id"
                  class="sub-trait-row"
                  :class="{ 'in-pool': isInPool(st), negative: st.polarity === 'NEGATIVE', 'trait-disabled': st.enabled === false }"
                  @click="openTraitDetail(st)"
                  @contextmenu.prevent
                >
                  <div class="sub-trait-left">
                    <span class="sub-trait-name" :class="{ disabled: phase !== 'adding' || st.enabled === false }">{{ displayName(st.name) }}</span>
                    <span v-if="st.statement" class="sub-trait-statement">{{ st.statement }}</span>
                  </div>
                  <div class="sub-trait-right" @click.stop="playTrait(st)" :title="'Play ' + displayName(st.name)">
                    <div v-if="traitDiceGroups(st).length" class="trait-die-groups">
                      <div v-for="(group, gi) in traitDiceGroups(st)" :key="gi" class="trait-die-group">
                        <DieIcon
                          v-for="(die, i) in group"
                          :key="i"
                          :die="die"
                          class="trait-die-icon sub-trait-die"
                          :style="i ? { marginLeft: '-12px' } : null"
                        />
                      </div>
                    </div>
                    <span v-else-if="st.ratingType !== 'EMPTY'" class="trait-die" :class="`die-${resolvedDieType(st)}`">{{ resourceDisplay(st) }}</span>
                  </div>
                </div>
              </div>
            </template>
          <Button
            v-if="activeSheetView === 'traits' && nextSet"
            class="next-set-btn"
            variant="neutral"
            @click="goToNextSet"
          >Next: {{ nextSet.name }} →</Button>
        </div> <!-- .trait-list -->
      <div v-else-if="!showAddTrait" class="empty">{{ activeSheetView === 'profile' ? 'No profile traits' : 'No traits configured' }}</div>
      <Button v-if="(!overrideEntityId || gmMode) && !showAddTrait" class="add-trait-btn" variant="secondary" block @click="openAddTrait">+ Add Trait</Button>
      <Button v-if="isForeignSheet && !showAddTrait" class="add-trait-btn" variant="secondary" block @click="openAddRelationshipTrait">+ Add relationship trait</Button>
      <!-- 2-phase trait picker -->
      <div v-if="showAddTrait" class="trait-picker">
        <template v-if="addPhase === 'sets'">
          <h4>Pick a trait set</h4>
          <button v-for="ts in availableTraitSets" :key="ts.id" class="picker-item" @click="selectSet(ts)">{{ ts.name }}</button>
        </template>
        <template v-if="addPhase === 'traits'">
          <Button class="picker-back" variant="link" @click="addPhase = 'sets'">← {{ selectedTraitSet?.name }}</Button>
          <button v-for="t in filteredTraits" :key="t.id" class="picker-item" @click="addTrait(t)">
            {{ t.name }}
            <span v-if="t.defaultRatingType !== 'EMPTY'" class="picker-die">{{ t.defaultDieType }}</span>
          </button>
          <div v-if="!filteredTraits.length" class="empty">{{ emptySetMessage }}</div>
        </template>
        <Button class="picker-cancel" variant="neutral" block @click="showAddTrait = false">Cancel</Button>
      </div>
      </div> <!-- .sheet-scroll -->
      </template>
    </template>
    <div v-else class="empty empty-no-entity">
      <span>No entity loaded</span>
      <Button
        v-if="!gmMode && !isForeignSheet"
        variant="neutral"
        @click="$emit('openSettings')"
        title="Choose a character"
      >↩ Player settings</Button>
    </div>

    <Teleport to="body">
      <RollTableMenu
        v-if="rollTableMenu"
        :entity-id="entity.id"
        :table-id="rollTableMenu.tableId"
        :title="rollTableMenu.name"
        :entity-razmerit="entity.razmerit ?? 0"
        :mode="rollTableMenu.mode || 'apply'"
        :player-id="playerId"
        :main-entity-id="mainEntityId"
        @close="rollTableMenu = null"
      />
    </Teleport>
  </div>

</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useApi } from '../composables/useApi.js'
import { useEntityCache } from '../composables/entityCache.js'
import { perfMark } from '../composables/perfLog.js'
import { useScheduledEvents } from '../composables/useScheduledEvents.js'
import { usePersistedRef } from '../composables/usePersistedState.js'
import DiePicker from './DiePicker.vue'
import BlueBook from './BlueBook.vue'
import LifePathWizard from './LifePathWizard.vue'
import DieIcon from './DieIcon.vue'
import MediaImage from './MediaImage.vue'
import Button from '@/components/ui/Button.vue'
import RollTableMenu from './gm/RollTableMenu.vue'

const props = defineProps({
  entityId: { type: String, default: null },  // null = GM free-roam (B95); guards at use sites
  universe: { type: String, default: 'earth' },
  phase: { type: String, default: 'adding' },
  embedded: { type: Boolean, default: false },
  gmMode: { type: Boolean, default: false },
  externalPoolSources: { type: Array, default: null },
  overrideEntityId: { type: String, default: null },
  viewerEntityId: { type: String, default: null },
  playerOwnedEntityIds: { type: Array, default: () => [] },
  visible: { type: Boolean, default: true },
  playerId: { type: String, default: '' },
  mainEntityId: { type: String, default: '' },
})

const emit = defineEmits(['addToPool', 'removeFromPool', 'splitDie', 'removeByTsId', 'sfxToggled', 'stampSfx', 'openSettings', 'sheetViewChange'])

function displayName(name) {
  return name
    .split('_')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

const { loading, error, graphql, triggerSfx, spendResourceDie, recoverResourceDie, spendChallengeDie } = useApi()
const entityCache = useEntityCache()
const { fetchFor: fetchScheduledEvents, formatTimers } = useScheduledEvents()
const entity = ref(null)
const activeProjection = computed(() => {
  const e = entity.value
  if (!e || !e.projections) return null
  return e.projections.find((p) => p.id === e.currentProjection) || null
})
const sheetPortrait = computed(() => activeProjection.value?.sheetImage || entity.value?.sheetPortrait || '')
// Mirror sheetPortrait's resolution chain: the projection's sheet image when
// present, else the entity's resolved sheet portrait.
const sheetPortraitTransparent = computed(() => {
  if (activeProjection.value?.sheetImage) return !!activeProjection.value.sheetImageTransparent
  return !!entity.value?.sheetPortraitTransparent
})

// SFX owned at three surfaces beyond the per-trait cards:
//   - entity-level (entity.sfxIds)
//   - active projection (projection.sfxIds)
//   - trait-set-as-unit (traitSetSettings[].sfxIds)
const entitySfxIds = computed(() => entity.value?.sfxIds || [])
const projectionSfxIds = computed(() => activeProjection.value?.sfxIds || [])
// traitsetId → [{ id, sfxIds }] for the trait-set-as-unit grants.
const traitSetSettingsByTraitsetId = computed(() => {
  const m = {}
  for (const tss of (entity.value?.traitSetSettings || [])) {
    m[tss.traitsetId] = tss
  }
  return m
})

function traitsetSfxIds(ts) {
  const tss = traitSetSettingsByTraitsetId.value[ts.traitsetId]
  return (tss && tss.sfxIds) || []
}

function traitsetSettingSourceId(ts) {
  const tss = traitSetSettingsByTraitsetId.value[ts.traitsetId]
  return (tss && tss.id) || null
}
const traitSets = ref([])
const allTraitSettings = ref([])
const effectiveSettings = ref([])
const showAllTraits = ref(false)

// Running centrally-scheduled timers, reconnected to their owners for display.
const entityTimers = ref([])
const traitSettingTimers = ref([])

const timersByTraitId = computed(() => {
  const m = {}
  for (const ev of traitSettingTimers.value) {
    if (!m[ev.targetId]) m[ev.targetId] = []
    m[ev.targetId].push(ev)
  }
  return m
})

const entityTimerLabel = computed(() => {
  if (!entityTimers.value.length) return ''
  return entityTimers.value
    .map((ev) => formatTimers(ev.timers, ev.combine))
    .filter(Boolean)
    .join(' · ')
})

function traitTimerLabel(t) {
  const evs = timersByTraitId.value[t.id]
  if (!evs || !evs.length) return ''
  return evs
    .map((ev) => formatTimers(ev.timers, ev.combine))
    .filter(Boolean)
    .join(' · ')
}

async function fetchTimers() {
  const eid = props.overrideEntityId || props.entityId
  if (!eid) return
  const tsIds = (allTraitSettings.value || []).map((t) => t.id)
  const [ent, ts] = await Promise.all([
    fetchScheduledEvents('entity', eid),
    tsIds.length ? fetchScheduledEvents('trait_setting', null, tsIds) : Promise.resolve([]),
  ])
  entityTimers.value = ent || []
  traitSettingTimers.value = ts || []
}

function groupTraitSettings(settings) {
  const sets = {}
  for (const ts of settings || []) {
    const key = ts.traitsetName || 'Other'
    if (!sets[key]) sets[key] = []
    sets[key].push(ts)
  }
  return Object.entries(sets)
    .map(([name, traits]) => ({
      name,
      traits,
      traitsetId: traits[0]?.traitsetId ?? null,
      order: traits[0]?.traitsetOrder ?? 99,
      limit: traits[0]?.traitsetLimit ?? 1,
    }))
    .sort((a, b) => a.order - b.order)
    .map(({ name, traits, traitsetId, order, limit }) => ({ name, traits, traitsetId, limit }))
}

function recomputeTraitSets() {
  const src = showAllTraits.value ? allTraitSettings.value : effectiveSettings.value
  const settings = src || []
  profileTraits.value = settings.filter(t => t.ratingType === 'EMPTY')
  traitSets.value = groupTraitSettings(settings.filter(t => t.ratingType !== 'EMPTY'))
}

// ── Relationship widget (foreign sheets only) ──────
const relationship = ref(null)
const showRelEditor = ref(false)
const relDescription = ref('')
const relInput = ref(null)
const blueBookRef = ref(null)


const activeSheetView = usePersistedRef('sheet.activeView', 'traits')  // 'traits' | 'profile' | 'lifepath' | 'bluebook' | 'relation'
watch(activeSheetView, (v) => emit('sheetViewChange', v))

const isForeignSheet = computed(() =>
  props.overrideEntityId && props.overrideEntityId !== props.viewerEntityId
)

// ── Relation tab (foreign sheets) ───────────────────────────────
// Traits hanging off *our* outgoing edge to the sheet we're looking at — what we
// hold about them (`_from == viewerEntityId`, `_to == overrideEntityId`). The tab
// only exists when such an edge carries traits; a bare edge isn't worth a tab.
const relationTraits = computed(() => relationship.value?.relationTraits || [])
const showRelationTab = computed(() => !!isForeignSheet.value && relationTraits.value.length > 0)
// `activeSheetView` is persisted, so 'relation' can outlive the edge that
// justified it (refresh, relationship removed, sheet switched). Fall back
// whenever the tab isn't available — immediate, so a stale value is caught on
// mount too. Defined after `activeSheetView`/`isForeignSheet` so the immediate
// run has both.
watch(showRelationTab, (has) => {
  if (!has && activeSheetView.value === 'relation') activeSheetView.value = 'traits'
}, { immediate: true })

const ownsCharacter = computed(() => {
  const id = props.overrideEntityId || props.entityId
  if (!props.playerOwnedEntityIds?.length) return false
  return props.playerOwnedEntityIds.includes(id)
})

// ── Projection (body) name — the sheet's undertitle ──────────────
// The title is always the character's name; the body they're currently in is
// named underneath it. Only your own sheet edits it — on a foreign sheet the
// name is read-only (the GM panel owns projection editing).
const editingProjectionName = ref(false)
const projectionNameValue = ref('')
const projectionNameInput = ref(null)
const savingProjectionName = ref(false)
const projectionSubtitle = computed(() => (activeProjection.value?.name || '').trim())
const canEditProjectionName = computed(() => !isForeignSheet.value && !!activeProjection.value)

function startProjectionNameEdit() {
  projectionNameValue.value = projectionSubtitle.value
  editingProjectionName.value = true
  nextTick(() => projectionNameInput.value?.focus())
}

async function commitProjectionName() {
  if (!editingProjectionName.value) return
  editingProjectionName.value = false          // also guards double-commit on blur+enter
  const projection = activeProjection.value
  if (!projection || savingProjectionName.value) return
  const name = projectionNameValue.value.trim()
  if (name === projectionSubtitle.value) return
  savingProjectionName.value = true
  try {
    await graphql(
      `mutation($id: ID!, $name: String) { updateProjection(projectionId: $id, name: $name) { id name } }`,
      { id: projection.id, name },
    )
    await fetchEntity()
  } catch (e) {
    console.error('updateProjection failed:', e)
    alert('Could not rename this projection.')
  } finally {
    savingProjectionName.value = false
  }
}


// Resolved human-readable names
const locationName = ref('')
const universeName = ref('')
const universeNames = ref({})  // universe key/id → display name

// Trait-set navigation — at most one set drilled into at a time.
const activeSetName = ref(null)
// Traits with an EMPTY rating type, shown flat on the profile tab.
const profileTraits = ref([])

function openSet(name) {
  activeSetName.value = name
}

function closeSet() {
  activeSetName.value = null
}

function goToTraitSets() {
  activeSheetView.value = 'traits'
  cancelEdit()
  activeSetName.value = null
}

// Collapse the drilled-in set when the sheet is hidden, so it re-opens clean.
watch(() => props.visible, (v) => {
  if (!v && activeSetName.value) activeSetName.value = null
})

const currentSet = computed(() => {
  if (!activeSetName.value) return null
  return traitSets.value.find(ts => ts.name === activeSetName.value) || null
})

const currentTraits = computed(() => {
  if (activeSheetView.value === 'relation') return relationTraits.value
  if (activeSheetView.value === 'profile') return profileTraits.value
  return currentSet.value?.traits || []
})

const currentSetReachedLimit = computed(() => {
  if (!currentSet.value || !currentSet.value.limit) return false
  return currentSet.value.traits.filter(t => isInPool(t)).length >= currentSet.value.limit
})

const nextSet = computed(() => {
  const idx = traitSets.value.findIndex(ts => ts.name === activeSetName.value)
  if (idx === -1) return null
  return traitSets.value[idx + 1] || null
})

function goToNextSet() {
  if (nextSet.value) activeSetName.value = nextSet.value.name
}

// SFX usage tracking — reset per dice pool cycle
const sfxActivations = ref({})
const sfxCatalog = ref({})  // sfxId → { name, description }
const availableSfxIds = ref(null)  // null = not loaded; else the conditions-filtered id list
const rollTableMenu = ref(null)  // { sfxId, tableId, name } | null
const SFX_PHASES = {
  'sfx-hinder': ['adding'],
  'sfx-spray-n-pray': ['adding'],
}
const poolSources = ref([])

// Trait-setting ids routed to the opponent's pool (negative traits offered
// during a contest) — highlighted in the sheet and counted toward the set limit.
const offeredTraits = ref(new Set())

// Track resource trait dice that have been spent into the pool
// { tsId: [dieType, ...] } — cleared when a die is removed from the pool
const spentResources = ref({})

// Trait editing (full-panel view)
const editingTraitId = usePersistedRef('sheet.editTraitId', null)

// trait id → display name, for resolving possible sub-trait candidates.
const traitNameMap = ref({})
async function ensureTraitNames() {
  if (Object.keys(traitNameMap.value).length) return
  try {
    const data = await graphql(`query($u: String!) { traitsByUniverse(universe: $u) { id name } }`, { u: props.universe })
    const m = {}
    for (const t of (data?.traitsByUniverse || [])) m[t.id] = t.name
    traitNameMap.value = m
  } catch { /* leave map empty; candidates fall back to slug names */ }
}

const editingTrait = computed(() => {
  if (!editingTraitId.value) return null
  for (const ts of traitSets.value) {
    const t = ts.traits.find(t => t.id === editingTraitId.value)
    if (t) return t
  }
  return profileTraits.value.find(t => t.id === editingTraitId.value) || null
})

function slugTraitId(id) {
  return String(id).replace(/^trait-/, '').replace(/-[a-z0-9]{4}$/i, '').replace(/-/g, ' ')
}

const availableSubtraits = computed(() => {
  const assigned = new Set((editingTrait.value?.subTraitSettings || []).map(st => st.traitId))
  return (editingTrait.value?.possibleSubtraitIds || [])
    .filter(id => !assigned.has(id))
    .map(id => ({ id, name: traitNameMap.value[id] || slugTraitId(id) }))
})

const editDice = usePersistedRef('sheet.editDice', [])
const editRatingType = usePersistedRef('sheet.editRatingType', 'STATIC')
const editPolarity = usePersistedRef('sheet.editPolarity', null)
const editCapacity = usePersistedRef('sheet.editCapacity', [])
const editStatement = usePersistedRef('sheet.editStatement', '')
const editNotes = usePersistedRef('sheet.editNotes', '')
const showDiePicker = ref(false)
const pickIdx = ref(0)
const pickedDie = ref('')
const showCapacityPicker = ref(false)
const capacityPickIdx = ref(0)
const pickedCapacityDie = ref('')
const editSfxIds = usePersistedRef('sheet.editSfxIds', [])
const editIsEgo = usePersistedRef('sheet.editIsEgo', true)
const editProjectionId = usePersistedRef('sheet.editProjectionId', null)
const showProjectionPicker = ref(false)

const RATING_TYPES = [
  { id: 'STATIC', label: 'Static' },
  { id: 'RESOURCE', label: 'Resource' },
  { id: 'CHALLENGE', label: 'Challenge' },
  { id: 'EMPTY', label: 'Empty' },
]

const editProjectionOptions = computed(() => entity.value?.projections || [])
const editProjectionName = computed(() => {
  const p = editProjectionOptions.value.find((p) => p.id === editProjectionId.value)
  return p ? (p.name || universeDisplay(p.originUniverse)) : (editProjectionId.value || 'select projection')
})
let longPressTimer = null

// ── Add trait picker ────────────────────────────
const showAddTrait = ref(false)
const addPhase = ref('sets')
const addMode = ref('trait')  // 'trait' | 'relationship'
const availableTraitSets = ref([])
const availableTraits = ref([])
const selectedTraitSet = ref(null)

const filteredTraits = computed(() => {
  if (!selectedTraitSet.value) return []
  // A set with allow_duplicates can hold several instances of the same trait
  // definition (e.g. two weapons, distinguished by statement), so don't drop
  // already-assigned traits there. Otherwise a trait may be assigned once.
  if (selectedTraitSet.value.allowDuplicates) {
    return availableTraits.value.filter(t => t.traitsetId === selectedTraitSet.value.id)
  }
  const assigned = new Set([
    ...traitSets.value.flatMap(ts => ts.traits.map(t => t.traitId || t.id)),
    ...profileTraits.value.map(t => t.traitId || t.id),
  ])
  return availableTraits.value.filter(t =>
    t.traitsetId === selectedTraitSet.value.id && !assigned.has(t.id)
  )
})

const totalInSet = computed(() => {
  if (!selectedTraitSet.value) return 0
  return availableTraits.value.filter(t => t.traitsetId === selectedTraitSet.value.id).length
})

const emptySetMessage = computed(() => {
  if (!selectedTraitSet.value) return ''
  if (totalInSet.value === 0) return 'No traits available in this set'
  return 'All traits in this set are already assigned'
})

async function openAddTrait() {
  addMode.value = 'trait'
  addPhase.value = 'sets'
  selectedTraitSet.value = null
  // Trait sets come from the entity being viewed (a foreign location may live
  // in a different universe than the acting character).
  const u = entity.value?.currentUniverse || props.universe
  const [tsData, trData] = await Promise.all([
    graphql(`query($u: String!) { traitsetsByUniverse(universe: $u) { id name order limit entityTypes allowDuplicates } }`, { u }),
    graphql(`query($u: String!) { traitsByUniverse(universe: $u) { id name traitsetId defaultDieType defaultRatingType } }`, { u }),
  ])
  const etype = entity.value?.type || ''
  if (tsData?.traitsetsByUniverse) {
    availableTraitSets.value = tsData.traitsetsByUniverse
      .filter(ts => !ts.entityTypes || ts.entityTypes.length === 0 || ts.entityTypes.includes(etype))
      .sort((a, b) => (a.order ?? 99) - (b.order ?? 99))
  }
  if (trData?.traitsByUniverse) {
    availableTraits.value = trData.traitsByUniverse
  }
  // If already drilled into a trait set, preselect it and jump straight to its traits.
  if (activeSetName.value) {
    const current = availableTraitSets.value.find(ts => ts.id === currentSet.value?.traitsetId)
    if (current) selectSet(current)
  }
  showAddTrait.value = true
}

async function openAddRelationshipTrait() {
  addMode.value = 'relationship'
  addPhase.value = 'sets'
  selectedTraitSet.value = null
  // Relationship traits are universe-agnostic: offer every trait set that is
  // usable on the 'relation' entity type.
  const tsData = await graphql(`query { traitsets { id name order limit entityTypes allowDuplicates } }`)
  const relationSets = (tsData?.traitsets || [])
    .filter(ts => (ts.entityTypes || []).includes('RELATION'))
    .sort((a, b) => (a.order ?? 99) - (b.order ?? 99))
  availableTraitSets.value = relationSets
  const ids = relationSets.map(ts => ts.id)
  if (ids.length) {
    const trData = await graphql(
      `query($ids: [ID!]!) { traitsByTraitsets(traitsetIds: $ids) { id name traitsetId defaultDieType defaultRatingType } }`,
      { ids },
    )
    availableTraits.value = trData?.traitsByTraitsets || []
  } else {
    availableTraits.value = []
  }
  showAddTrait.value = true
}

function selectSet(ts) {
  selectedTraitSet.value = ts
  addPhase.value = 'traits'
}

async function addTrait(trait) {
  if (addMode.value === 'relationship') {
    const result = await graphql(`mutation($from: ID!, $to: ID!, $traitId: ID!, $die: DieType!) {
      addRelationshipTrait(fromEntityId: $from, toEntityId: $to, traitId: $traitId, die: $die) { id }
    }`, {
      from: props.viewerEntityId,
      to: props.overrideEntityId,
      traitId: trait.id,
      die: (trait.defaultDieType || 'd6').toUpperCase(),
    })
    if (!result?.addRelationshipTrait) {
      console.error('addRelationshipTrait failed:', error.value || 'unknown error')
      return
    }
    showAddTrait.value = false
    addPhase.value = 'sets'
    selectedTraitSet.value = null
    fetchEntity()
    return
  }

  const result = await graphql(`mutation($eid: ID!, $input: TraitSettingInput!) {
    addTraitSetting(entityId: $eid, input: $input) { id name traitsetName }
  }`, {
    eid: props.overrideEntityId || props.entityId,
    input: {
      traitId: trait.id,
      traitsetId: selectedTraitSet.value.id,
      dice: [(trait.defaultDieType || 'd6').toUpperCase()],
      ratingType: (trait.defaultRatingType || 'STATIC').toUpperCase(),
    },
  })
  if (!result?.addTraitSetting) {
    console.error('addTrait failed:', error.value || 'unknown error')
    return
  }
  showAddTrait.value = false
  addPhase.value = 'sets'
  selectedTraitSet.value = null
  fetchEntity()
}

// ── Trait detail (read-only) ────────────────────────────────────
// The row's third click zone. Playing the trait moved to the rating zone; the
// name / statement / empty space of the row now opens the trait read-only, with
// its full SFX, notes and tags. `contextmenu` still opens the editor.
const detailTrait = ref(null)

function openTraitDetail(t) {
  // A touch long-press fires startEdit on touchstart and the click on release,
  // so the editor can already be open by the time this runs — don't stack the
  // detail panel behind it.
  if (editingTraitId.value) return
  detailTrait.value = t
}

function closeTraitDetail() {
  detailTrait.value = null
}

// The detail panel sits ahead of the tab branches in the render chain, so a tab
// change would otherwise leave it covering the newly chosen view.
watch(activeSheetView, () => { detailTrait.value = null })

function ratingTypeLabel(t) {
  return RATING_TYPES.find(rt => rt.id === t.ratingType)?.label || t.ratingType || ''
}

// Same gates playTrait() applies — the detail only offers the play affordance
// when playing would actually do something. An EMPTY (profile) or depleted
// trait has no die to play, so it gets no hint and no sub-trait play button.
function canPlayTrait(t) {
  if (props.phase !== 'adding' || t.enabled === false) return false
  if (t.ratingType === 'EMPTY') return false
  return (t.dice || []).length > 0
}

// Rows for the detail's CONTEXT block. Only what actually applies is returned,
// so the block collapses entirely for a plain static trait.
function detailContext(t) {
  const rows = []
  if (t.ego === false) {
    rows.push({ label: 'body', value: t.universe ? `projection · ${universeDisplay(t.universe)}` : 'projection' })
  }
  if (t.relationshipContactName) rows.push({ label: 'toward', value: t.relationshipContactName })
  if (t.knownTo?.length) {
    rows.push({ label: 'known to', value: `${t.knownTo.length} ${t.knownTo.length === 1 ? 'entity' : 'entities'}` })
  }
  const timer = traitTimerLabel(t)
  if (timer) rows.push({ label: 're-enables', value: timer })
  return rows
}

// ── Playing a trait (rating zone) ───────────────────
async function playTrait(t) {
  if (props.phase !== 'adding') return
  if (t.enabled === false) return  // disabled trait contributes no dice

  // Resource traits: the row click spends only when the pool has a single
  // die type; mixed-type resources are spent per die group.
  if (t.ratingType === 'RESOURCE') {
    const types = [...new Set((t.dice || []).map(d => (typeof d === 'string' ? d.toLowerCase() : d)))]
    if (types.length === 1) await spendResourceGroup(t, types[0])
    return
  }

  // Challenge traits: same single-vs-mixed-type split as resources. The row
  // click spends one die; mixed-type pools are spent per die group.
  if (t.ratingType === 'CHALLENGE') {
    const types = [...new Set((t.dice || []).map(d => (typeof d === 'string' ? d.toLowerCase() : d)))]
    if (types.length === 1) await spendChallengeGroup(t, types[0])
    return
  }

  const negative = t.polarity === 'NEGATIVE'
  const dieType = (t.dice && t.dice.length ? t.dice[0] : '').toLowerCase()

  // Multi-die static traits contribute one pool die per rating entry.
  if (t.ratingType === 'STATIC' && (t.dice || []).length > 1) {
    emit('addToPool', { dice: t.dice.map(d => d.toLowerCase()), source: t.name, label: displayName(t.name), tsId: t.id, negative, armedSfxIds: armedSfxIdsForTrait(t) })
    return
  }

  if (!dieType) return  // no die rating — nothing to add
  emit('addToPool', { die: dieType, source: t.name, label: displayName(t.name), tsId: t.id, negative, armedSfxIds: armedSfxIdsForTrait(t) })
}

async function spendResourceGroup(t, dieType) {
  // Spend one die of the chosen type from the resource and add it to the pool.
  if (props.phase !== 'adding') return
  if (t.enabled === false) return
  await spendResourceDie(t.id, dieType)
  if (!spentResources.value[t.id]) spentResources.value[t.id] = []
  spentResources.value[t.id].push(dieType)
  emit('addToPool', { die: dieType, source: t.name, label: displayName(t.name), tsId: t.id, negative: t.polarity === 'NEGATIVE', resource: true, armedSfxIds: armedSfxIdsForTrait(t) })
  await fetchEntity()
}

async function spendChallengeGroup(t, dieType) {
  // Spend one die from a challenge pool and route it per polarity:
  // negative (doom) → destination "opposition" (plain die, routes to opposition);
  // positive (progress) → destination "pool" (flagged resource, joins own pool).
  if (props.phase !== 'adding') return
  if (t.enabled === false) return
  const destination = t.polarity === 'NEGATIVE' ? 'opposition' : 'pool'
  const res = await spendChallengeDie(t.id, dieType, destination)
  if (!res) return
  t.dice = (res.dice || []).map(d => d.toUpperCase())
  emit('addToPool', {
    die: res.die.toLowerCase(),
    source: t.name,
    label: displayName(t.name),
    tsId: t.id,
    negative: t.polarity === 'NEGATIVE',
    resource: res.resource,
    armedSfxIds: armedSfxIdsForTrait(t),
  })
  await fetchEntity()
}

function resolvedDieType(t) {
  // Return the die type for CSS class (determines color)
  if (t.dice && t.dice.length > 0) return t.dice[0].toLowerCase()
  return (t.dieType || 'd6').toLowerCase()
}

function resourceDisplay(t) {
  // Show available dice for resource traits, rating string for static traits
  if (t.ratingType === 'EMPTY') return ''
  if (t.ratingType === 'RESOURCE') {
    if (t.dice && t.dice.length === 0) return 'depleted'
    return t.rating || 'empty'
  }
  return t.rating || (t.dice ? t.dice.join(', ') : '')
}

function challengeProgressLabel(t) {
  // Progress/ceiling indicator for challenge pools when a capacity is set:
  // positive → "n/m" progress toward target; negative → "n/m" against ceiling.
  if (t.ratingType !== 'CHALLENGE') return ''
  const cap = (t.capacity || []).length
  if (!cap) return ''
  return `${(t.dice || []).length}/${cap}`
}

function groupByDieType(dice) {
  // Group a dice array by type so each type forms its own little
  // staircase (e.g. 3d4 + 2d6 → [['d4','d4','d4'], ['d6','d6']]).
  const groups = []
  const byType = new Map()
  for (const d of (dice || [])) {
    const die = d.toLowerCase()
    if (!byType.has(die)) {
      const group = []
      byType.set(die, group)
      groups.push(group)
    }
    byType.get(die).push(die)
  }
  // Ascending die size: d4 → d6 → d8 → d10 → d12.
  groups.sort((a, b) => parseInt(a[0].slice(1), 10) - parseInt(b[0].slice(1), 10))
  return groups
}

function traitDiceGroups(t) {
  // Static traits render grouped dice.  Resources/challenge/empty have their
  // own rendering (resources use resourceDiceGroups/resourceSpentGroups,
  // challenge uses its own die-stack branch).
  if (t.ratingType === 'RESOURCE' || t.ratingType === 'EMPTY' || t.ratingType === 'CHALLENGE') return []
  return groupByDieType(t.dice)
}

function resourceDiceGroups(t) {
  return groupByDieType(t.dice)
}

function resourceSpentGroups(t) {
  return groupByDieType(t.spentDice)
}

function isResourceDepleted(t) {
  // Resources and challenge pools show a dimmed "depleted/empty" state when
  // their spendable dice ledger is empty.
  if (t.ratingType !== 'RESOURCE' && t.ratingType !== 'CHALLENGE') return false
  return (!t.dice || t.dice.length === 0)
}

async function recoverSpentDie(die) {
  // Recover one spent die back into the resource pool (editor affordance).
  // Patch local state from the REST response so both the recoverable row
  // and the available-dice chips update without a full refetch.
  const t = editingTrait.value
  if (!t) return
  const res = await recoverResourceDie(t.id, die.toLowerCase())
  if (!res) return
  const toUpper = (arr) => (arr || []).map((d) => d.toUpperCase())
  t.dice = toUpper(res.dice)
  t.spentDice = toUpper(res.spent)
  t.rating = null  // force fallback to dice display
  editDice.value = (res.dice || []).map((d) => d.toLowerCase())
}

function isInPool(t) {
  return poolSources.value.includes(t.id) || offeredTraits.value.has(t.id)
}

function isOffered(t) {
  return offeredTraits.value.has(t.id)
}

function setOfferedTraits(ids) {
  offeredTraits.value = new Set(ids || [])
}

function isKnown(t) {
  // The GM sees every trait — fog of war (knownTo) only applies to players.
  if (props.gmMode) return true
  if (!props.overrideEntityId || !props.viewerEntityId) return true
  if (props.overrideEntityId === props.entityId) return true
  return (t.knownTo || []).includes(props.viewerEntityId)
}

function inPoolCount(ts) {
  return ts.traits.filter(t => isInPool(t)).length
}

function sfxAllowedInPhase(sfxId) {
  const allowed = SFX_PHASES[sfxId] || ['adding']
  return allowed.includes(props.phase)
}

// Pool state tracking — called by DiceRoller via App
function setPoolSources(sources) {
  // sources is now [{ die, label, tsId }, ...] — track by tsId
  poolSources.value = sources.map(s => s.tsId).filter(Boolean)

  // When the current set fills to its limit, advance to the next set's list.
  const sets = traitSets.value
  const idx = sets.findIndex(s => s.name === activeSetName.value)
  if (idx !== -1) {
    const count = sets[idx].traits.filter(t => poolSources.value.includes(t.id)).length
    if (sets[idx].limit && count >= sets[idx].limit) {
      activeSetName.value = sets[idx + 1] ? sets[idx + 1].name : null
    }
  }

  // Auto-recover resource dice that were removed from the pool
  // (e.g. via chip click in DiceRoller).  Only during adding phase —
  // once dice are rolled they stay spent.
  if (props.phase !== 'adding') return
  let recovered = false
  for (const tsId of Object.keys(spentResources.value)) {
    const spent = [...spentResources.value[tsId]]
    const inPool = sources.filter(s => s.tsId === tsId).map(s => s.die)
    const remaining = []
    for (const dieType of spent) {
      const at = inPool.indexOf(dieType)
      if (at !== -1) {
        inPool.splice(at, 1)
        remaining.push(dieType)
      } else {
        recoverResourceDie(tsId, dieType)
        recovered = true
      }
    }
    if (remaining.length) spentResources.value[tsId] = remaining
    else delete spentResources.value[tsId]
  }
  if (recovered) fetchEntity()
}

defineExpose({ resetSfxCounts, setPoolSources, setRazmerit, setOfferedTraits, fetchEntity, refreshBlueBook: () => blueBookRef.value?.refresh() })

function sfxActive(sfxId) {
  return (sfxActivations.value[sfxId] || 0) > 0
}

function armedSfxIdsForTrait(t) {
  // SFX attached to this trait that the player has armed (activated) this roll.
  return (t.sfxIds || []).filter(sfxId => sfxActive(sfxId))
}

function sfxUsed(sfxId) {
  if (!sfxAllowedInPhase(sfxId)) return true
  if (sfxActive(sfxId)) return true
  if (sfxId === 'sfx-spray-n-pray' && !poolSources.value.includes('shooting')) return true
  return false
}

function sfxName(sfxId) {
  return sfxCatalog.value[sfxId]?.name || sfxId.replace(/^sfx-/, '').replace(/-/g, ' ')
}

function sfxDescription(sfxId) {
  return sfxCatalog.value[sfxId]?.description || ''
}

// The derived natural-language rules text ("Activated: spend 1 razmerit."), as
// opposed to `description`, which is the author's flavour lead-in. Cards show
// both; the compact row cards keep to the flavour line.
function sfxCardText(sfxId) {
  return sfxCatalog.value[sfxId]?.cardText || ''
}

// A roll-table-as-menu SFX carries a single roll_table/menu effect whose
// ``target`` is the table id. Clicking it opens the picker instead of firing.
function rollTableMenuEffect(sfxId) {
  const sfx = sfxCatalog.value[sfxId]
  if (!sfx) return null
  return (sfx.effects || []).find(e => e.type === 'roll_table' && e.action === 'menu') || null
}

// A condition-blocked SFX is owned (it appears on the sheet) but its static
// conditions (e.g. source_rating, entity_type) fail at this moment, so it can't
// fire. ``null`` means availability hasn't loaded yet (don't block optimistically).
function sfxConditionBlocked(sfxId) {
  if (availableSfxIds.value == null) return false
  return !availableSfxIds.value.includes(sfxId)
}

function sfxTitle(sfxId) {
  if (sfxConditionBlocked(sfxId)) return `${sfxName(sfxId)} (conditions not met)`
  return sfxActive(sfxId) ? `Deactivate ${sfxName(sfxId)}` : `Activate ${sfxName(sfxId)}`
}

async function fetchAvailableSfxIds() {
  const id = props.overrideEntityId || props.entityId
  if (!id) { availableSfxIds.value = null; return }
  try {
    const data = await graphql(
      `query($id: ID!, $u: String!) { availableSfxIds(entityId: $id, universe: $u) }`,
      { id, u: props.universe },
    )
    availableSfxIds.value = (data?.availableSfxIds || []).map(String)
  } catch (e) {
    console.error('fetchAvailableSfxIds', e)
    availableSfxIds.value = null
  }
}

async function fetchSfxCatalog() {
  try {
    const r = await fetch('/api/v1/graphql', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: `query { sfxs { id name description cardText effects { timing type action target entity result } } }` }),
    })
    const json = await r.json()
    const map = {}
    for (const s of json?.data?.sfxs || []) map[s.id] = s
    sfxCatalog.value = map
  } catch (e) {
    console.error('fetchSfxCatalog', e)
  }
}

function resetSfxCounts() {
  sfxActivations.value = {}
  spentResources.value = {}
}

const QUERY = `
  query($id: ID!) {
    entity(id: $id) {
      type
      name
      razmerit
      currentUniverse
      currentLocation
      currentProjection
      backgroundImage
      sheetPortrait
      sheetPortraitTransparent
      sfxIds
      projections {
        id originUniverse universe name sheetImage sheetImageTransparent currentLocation transversalType sfxIds
      }
      traitSetSettings {
        id traitsetId sfxIds
      }
      traitSettings {
        id
        traitId
        traitsetId
        name
        traitsetName
        dieType
        ratingType
        rating
        ego
        fromType
        projectionId
        statement
        notes
        sfxIds
        universe
        dice
        spentDice
        capacity
        polarity
        enabled
        traitsetOrder
        traitsetLimit
        knownTo
        possibleSfxIds
        tags
        relationshipContactId
        relationshipContactName
        relationshipContactType
        relationshipType
        possibleSubtraitIds
        subTraitSettings {
          id
          traitId
          name
          dieType
          ratingType
          rating
          fromType
          statement
          sfxIds
          dice
          spentDice
          capacity
          polarity
          enabled
        }
      }
      effectiveTraitSettings {
        id
        traitId
        traitsetId
        name
        traitsetName
        dieType
        ratingType
        rating
        ego
        fromType
        projectionId
        statement
        notes
        sfxIds
        universe
        dice
        spentDice
        capacity
        polarity
        enabled
        traitsetOrder
        traitsetLimit
        knownTo
        possibleSfxIds
        tags
        relationshipContactId
        relationshipContactName
        relationshipContactType
        relationshipType
        possibleSubtraitIds
        subTraitSettings {
          id
          traitId
          name
          dieType
          ratingType
          rating
          fromType
          statement
          sfxIds
          dice
          spentDice
          capacity
          polarity
          enabled
        }
      }
    }
  }
`

async function fetchEntity() {
  const id = props.overrideEntityId || props.entityId
  if (!id) return
  const data = await graphql(QUERY, { id })
  if (data?.entity) {
    entityCache.setSheet(id, data.entity)
    applyEntity(data.entity)
    perfMark('sheet-loaded', { id, cached: false })
  }
}

// Render the cached sheet immediately when we have it; otherwise fetch fresh.
// Used on open/switch so re-opening a sheet doesn't re-download the whole entity.
let inflightLoad = null // { id, promise } — dedupe concurrent cache-miss loads

function loadCachedEntity() {
  const id = props.overrideEntityId || props.entityId
  if (!id) return
  const cached = entityCache.getSheet(id)
  if (cached) {
    applyEntity(cached)
    perfMark('sheet-loaded', { id, cached: true })
    return
  }
  // Dedupe: a concurrent load for the same entity (e.g. the universe watcher
  // refiring while the first fetch is still in flight) shares the in-flight
  // request instead of starting a second full fetch.
  if (inflightLoad && inflightLoad.id === id) {
    return
  }
  const promise = fetchEntity()
  inflightLoad = { id, promise }
  promise.finally(() => {
    if (inflightLoad && inflightLoad.id === id) inflightLoad = null
  })
}

function applyEntity(e) {
  entity.value = e
  resolveNames(e)
  allTraitSettings.value = e.traitSettings || []
  effectiveSettings.value = e.effectiveTraitSettings || []
  recomputeTraitSets()
  fetchTimers()
  fetchAvailableSfxIds()
}

async function resolveNames(e) {
  if (e.currentLocation) {
    try {
      const r = await fetch(`/api/v1/locations/${e.currentLocation}/navigate`)
      const nav = await r.json()
      locationName.value = nav.location?.name || e.currentLocation
    } catch { locationName.value = e.currentLocation }
  }
  if (e.currentUniverse) {
    try {
      const r = await fetch('/api/v1/graphql', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: `{ entities(type: UNIVERSE) { id name currentUniverse } }` })
      })
      const json = await r.json()
      const universes = json.data?.entities || []
      const map = {}
      for (const u of universes) {
        if (u.currentUniverse) map[u.currentUniverse] = u.name
        if (u.id) map[u.id] = u.name
      }
      universeNames.value = map
      const match = universes.find(u => u.currentUniverse === e.currentUniverse || u.id === e.currentUniverse)
      universeName.value = match?.name || e.currentUniverse
    } catch { universeName.value = e.currentUniverse }
  }
}

function universeDisplay(key) {
  return universeNames.value[key] || key
}

// Find the traitsetting ID that owns a given SFX
function findTsIdForSfx(sfxId) {
  for (const ts of traitSets.value) {
    for (const t of ts.traits) {
      if ((t.sfxIds || []).includes(sfxId)) return t.id
    }
  }
  return null
}

async function activateSfx(sfxId, sourceId = null) {
  const menu = rollTableMenuEffect(sfxId)
  if (menu && menu.target) {
    const isSupportCast = sfxId === 'sfx-roll-support-cast'
    let tableId = menu.target
    if (isSupportCast) {
      // B65 — support-cast tables are universe-scoped: resolve from the main's
      // current universe (falling back to the generic table) before opening.
      const mainId = props.mainEntityId || props.entityId
      const data = await graphql(
        `query($id: ID!) { supportCastTableId(entityId: $id) }`,
        { id: mainId },
      )
      tableId = data?.supportCastTableId || null
      if (!tableId) return
    }
    rollTableMenu.value = {
      sfxId, tableId, name: sfxName(sfxId),
      mode: isSupportCast && props.playerId && props.mainEntityId
        ? 'create-support' : 'apply',
    }
    return
  }

  const active = sfxActive(sfxId)

  if (!active) {
    // Activate. If the SFX declares a source kind, pass the surface it was
    // clicked from (the trait instance id) as ``source_id`` so the backend
    // binds it to the declared ``{variable}``.
    await triggerSfx(props.entityId, sfxId, props.universe, { phase: props.phase, ...(sourceId ? { source_id: sourceId } : {}) })
    sfxActivations.value[sfxId] = 1
    // Re-stamp dice already in the pool (armed after adding).
    const tsId = findTsIdForSfx(sfxId)
    if (tsId) emit('stampSfx', { tsId, sfxId })
    await fetchEntity()

    if (sfxId === 'sfx-hinder') {
      const tsId = findTsIdForSfx('sfx-hinder')
      emit('removeByTsId', tsId)
      emit('addToPool', { die: 'd4', source: 'hinder', label: 'Hinder d4', tsId })
    }
    if (sfxId === 'sfx-spray-n-pray') {
      emit('splitDie', { source: 'shooting', label: 'Spray' })
    }
    emit('sfxToggled', { sfxId, active: true })
  } else {
    // Deactivate (reverse)
    sfxActivations.value[sfxId] = 0

    if (sfxId === 'sfx-hinder') {
      const tsId = findTsIdForSfx('sfx-hinder')
      emit('removeByTsId', tsId)
      // Reverse razmerit: spend 1
      await triggerSfx(props.entityId, 'sfx-hinder', props.universe, { reverse: true })
    }
    if (sfxId === 'sfx-spray-n-pray') {
      emit('removeFromPool', 'shooting-a')
      emit('removeFromPool', 'shooting-b')
      await triggerSfx(props.entityId, 'sfx-spray-n-pray', props.universe, { reverse: true })
    }
    emit('sfxToggled', { sfxId, active: false })
    await fetchEntity()
  }
}

// ── Inline trait editing ──────────────────────────

function startEdit(t) {
  if (deleteCountdown.value > 0) {
    clearInterval(deleteTimer)
    deleteCountdown.value = 0
    const targetId = deletingTraitId.value
    deletingTraitId.value = null
    deleteTrait({ id: targetId })
  }
  editingTraitId.value = t.id
  detailTrait.value = null
  ensureTraitNames()
  editDice.value = (t.dice || []).map(d => d.toLowerCase())
  editCapacity.value = (t.capacity || []).map(d => d.toLowerCase())
  editRatingType.value = t.ratingType || 'STATIC'
  editPolarity.value = t.polarity || null
  editStatement.value = t.statement || ''
  editNotes.value = t.notes || ''
  editSfxIds.value = [...(t.sfxIds || [])]
  const isMorph = t.fromType === 'projection' || t.ego === false
  editIsEgo.value = !isMorph
  editProjectionId.value =
    (t.fromType === 'projection' && t.projectionId) ||
    (isMorph ? (entity.value?.currentProjection || entity.value?.projections?.[0]?.id) : null) ||
    null
  showProjectionPicker.value = false
  showDiePicker.value = false
  showCapacityPicker.value = false
}

function cancelEdit() {
  if (deleteCountdown.value > 0) {
    clearInterval(deleteTimer)
    deleteCountdown.value = 0
    const targetId = deletingTraitId.value
    deletingTraitId.value = null
    deleteTrait({ id: targetId })
  } else {
    editingTraitId.value = null
  }
}

const deleteCountdown = ref(0)
const deletingTraitId = ref(null)
let deleteTimer = null

function onDeleteClick(t) {
  if (deleteCountdown.value > 0) {
    clearInterval(deleteTimer)
    deleteCountdown.value = 0
    deletingTraitId.value = null
    return
  }
  deleteCountdown.value = 3
  deletingTraitId.value = t.id
  deleteTimer = setInterval(() => {
    deleteCountdown.value--
    if (deleteCountdown.value <= 0) {
      clearInterval(deleteTimer)
      deletingTraitId.value = null
      deleteTrait(t)
    }
  }, 1000)
}

const showRazmeritWidget = ref(false)
const editingRazmerit = ref(false)
const razmeritInputValue = ref('')
const razmeritInput = ref(null)

function startRazmeritEdit() {
  editingRazmerit.value = true
  razmeritInputValue.value = String(entity.value?.razmerit ?? 0)
  nextTick(() => razmeritInput.value?.focus())
}

async function commitRazmerit() {
  if (!editingRazmerit.value) return
  editingRazmerit.value = false
  const val = parseInt(razmeritInputValue.value, 10)
  if (Number.isNaN(val)) return
  const resp = await fetch('/api/v1/graphql', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: 'mutation($id: ID!, $razmerit: Int) { updateEntity(input: { id: $id, razmerit: $razmerit }) { id razmerit } }',
      variables: { id: props.entityId, razmerit: val },
    }),
  })
  const data = await resp.json()
  const newVal = data?.data?.updateEntity?.razmerit
  if (newVal != null && entity.value) entity.value.razmerit = newVal
}

async function adjustRazmerit(delta) {
  const mutation = delta < 0 ? 'spendRazmerit' : 'earnRazmerit'
  const resp = await fetch('/api/v1/graphql', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: 'mutation($eid: ID!, $amt: Int!) { ' + mutation + '(entityId: $eid, amount: $amt) { fromBalance toBalance } }',
      variables: { eid: props.entityId, amt: Math.abs(delta) },
    }),
  })
  const data = await resp.json()
  const result = data?.data?.[mutation]
  const balance = mutation === 'earnRazmerit' ? result?.toBalance : result?.fromBalance
  if (balance != null) entity.value.razmerit = balance
}

function setRazmerit(balance, entityId) {
  // Live-patch the sheet when the SSE razmerit_changed event arrives for the
  // entity this sheet is currently showing (could be an override/peer).
  if (entity.value && balance != null && entity.value.id === (entityId ?? props.entityId)) {
    entity.value.razmerit = balance
  }
}

async function deleteTrait(t) {
  await fetch('/api/v1/graphql', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: `mutation($id: ID!) { removeTraitSetting(id: $id) }`, variables: { id: t.id } }),
  })
  editingTraitId.value = null
  // Remove from local traitSets / profileTraits — no full re-render
  let removed = false
  for (const ts of traitSets.value) {
    const idx = ts.traits.findIndex(tr => tr.id === t.id)
    if (idx !== -1) {
      ts.traits.splice(idx, 1)
      if (ts.traits.length === 0) {
        traitSets.value = traitSets.value.filter(s => s.name !== ts.name)
      }
      removed = true
      break
    }
  }
  if (!removed) {
    const idx = profileTraits.value.findIndex(tr => tr.id === t.id)
    if (idx !== -1) profileTraits.value.splice(idx, 1)
  }
}

function ensureEditProjection() {
  if (!editIsEgo.value && !editProjectionId.value) {
    editProjectionId.value = entity.value?.currentProjection || entity.value?.projections?.[0]?.id || null
  }
}

async function doSave() {
  if (!editingTraitId.value) return
  ensureEditProjection()
  const isRel = editingTrait.value?.fromType === 'relationship'
  const newDice = editDice.value.map(d => d.toUpperCase())
  const newCapacity = editCapacity.value.map(d => d.toUpperCase())
  const query = `mutation($id: ID!, $dice: [DieType!], $capacity: [DieType!], $ratingType: RatingType, $polarity: Polarity, $statement: String, $notes: String, $sfxIds: [ID!], $fromType: String, $projectionId: ID) {
    updateTraitSetting(id: $id, input: { dice: $dice, capacity: $capacity, ratingType: $ratingType, polarity: $polarity, statement: $statement, notes: $notes, sfxIds: $sfxIds, fromType: $fromType, projectionId: $projectionId }) { id }
  }`
  const variables = {
    id: editingTraitId.value,
    dice: newDice,
    capacity: newCapacity,
    ratingType: editRatingType.value,
    polarity: editPolarity.value,
    statement: editStatement.value ?? null,
    notes: editNotes.value ?? null,
    sfxIds: editSfxIds.value,
    // Relationship traits keep their anchor; only entity/projection traits toggle it.
    fromType: isRel ? null : (editIsEgo.value ? 'entity' : 'projection'),
    projectionId: isRel ? null : (editIsEgo.value ? null : editProjectionId.value),
  }
  await fetch('/api/v1/graphql', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, variables }),
  })
  // Patch local data — no full re-render
  const patchTrait = (t) => {
    t.dice = newDice
    t.capacity = newCapacity
    t.ratingType = editRatingType.value
    t.polarity = editPolarity.value
    t.rating = null  // force fallback to dice display
    t.sfxIds = [...editSfxIds.value]
    t.statement = editStatement.value
    t.notes = editNotes.value
    if (!isRel) {
      t.ego = editIsEgo.value
      t.fromType = editIsEgo.value ? 'entity' : 'projection'
      t.projectionId = editIsEgo.value ? null : editProjectionId.value
    }
  }
  for (const ts of traitSets.value) {
    const t = ts.traits.find(t => t.id === editingTraitId.value)
    if (t) { patchTrait(t); break }
  }
  const pt = profileTraits.value.find(t => t.id === editingTraitId.value)
  if (pt) patchTrait(pt)
}

async function toggleEgo() {
  editIsEgo.value = !editIsEgo.value
  if (!editIsEgo.value) {
    editProjectionId.value = entity.value?.currentProjection || entity.value?.projections?.[0]?.id || null
  }
  showProjectionPicker.value = false
  await doSave()
  await fetchEntity()
}

function togglePolarity() {
  editPolarity.value = editPolarity.value === 'POSITIVE' ? 'NEGATIVE' : 'POSITIVE'
  doSave()
}

function toggleProjectionPicker() {
  showProjectionPicker.value = !showProjectionPicker.value
}

async function selectProjection(p) {
  editProjectionId.value = p.id
  showProjectionPicker.value = false
  await doSave()
  await fetchEntity()
}

function toggleSfx(sfxId) {
  const idx = editSfxIds.value.indexOf(sfxId)
  if (idx === -1) editSfxIds.value.push(sfxId)
  else editSfxIds.value.splice(idx, 1)
  doSave()
}

async function setRatingType(rt) {
  if (editRatingType.value === rt) return
  editRatingType.value = rt
  // EMPTY traits carry no dice rating — clear them.
  if (rt === 'EMPTY') editDice.value = []
  await doSave()
  // Re-split so the trait moves between the rated list and the profile tab.
  recomputeTraitSets()
}

async function addSubTrait(traitId) {
  const parentId = editingTrait.value?.id
  if (!parentId) return
  await graphql(`mutation($parent: ID!, $trait: ID!) { addSubTrait(parentTraitsettingId: $parent, traitId: $trait) { id } }`, { parent: parentId, trait: traitId })
  await fetchEntity()
}

async function removeSubTrait(subId) {
  await graphql(`mutation($id: ID!) { removeSubTrait(subTraitSettingId: $id) }`, { id: subId })
  await fetchEntity()
}

let statementDebounce = null
function onStatementInput() {
  clearTimeout(statementDebounce)
  statementDebounce = setTimeout(doSave, 500)
}

function splitStatement() {
  const words = (editStatement.value || '').trim().split(/\s+/).filter(Boolean)
  if (words.length > 7) {
    const moved = editStatement.value.trim()
    editNotes.value = editNotes.value ? editNotes.value + '\n' + moved : moved
    editStatement.value = ''
  }
}

function onDiePicked(die) {
  if (!die) {
    editDice.value.splice(pickIdx.value, 1)
  } else if (pickIdx.value >= editDice.value.length) {
    editDice.value.push(die)
  } else {
    editDice.value.splice(pickIdx.value, 1, die)
  }
  showDiePicker.value = false
  doSave()
}

function onCapacityPicked(die) {
  if (!die) {
    editCapacity.value.splice(capacityPickIdx.value, 1)
  } else if (capacityPickIdx.value >= editCapacity.value.length) {
    editCapacity.value.push(die)
  } else {
    editCapacity.value.splice(capacityPickIdx.value, 1, die)
  }
  showCapacityPicker.value = false
  doSave()
}

// Long-press detection for touchscreens
function onTouchStart(t) {
  longPressTimer = setTimeout(() => startEdit(t), 600)
}

function onTouchEnd() {
  clearTimeout(longPressTimer)
}

// Close edit on Escape
function onKeydown(e) {
  if (e.key === 'Escape' && editingTraitId.value) cancelEdit()
}

// Close the razmerit popover when clicking outside its anchor.
function onDocumentClick(e) {
  if (showRazmeritWidget.value && !e.target.closest('.razmerit-anchor')) {
    showRazmeritWidget.value = false
  }
}

onMounted(() => {
  console.log('[diag] CharacterSheet mounted', { entityId: props.entityId, universe: props.universe, embedded: props.embedded })
  document.addEventListener('keydown', onKeydown)
  document.addEventListener('click', onDocumentClick)
})
onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('click', onDocumentClick)
})

onMounted(() => {
  console.log('[diag] CharacterSheet fetchEntity mounted', { entityId: props.entityId })
  loadCachedEntity()
  fetchSfxCatalog()
})
watch(() => props.entityId, loadCachedEntity)
watch(() => props.universe, loadCachedEntity)
watch(() => props.overrideEntityId, loadCachedEntity)
watch(() => [props.entityId, props.overrideEntityId], () => { activeSetName.value = null })
watch(showAllTraits, recomputeTraitSets)

// ── Relationship fetch ─────────────────────────────
async function fetchRelationship() {
  if (!props.viewerEntityId || !props.overrideEntityId) {
    relationship.value = null
    return
  }
  const query = `
    query($viewer: ID!, $target: ID!) {
      relationship(fromEntityId: $viewer, toEntityId: $target) {
        id
        description
        relationTraits {
          id
          traitId
          traitsetId
          name
          traitsetName
          dieType
          ratingType
          rating
          ego
          fromType
          projectionId
          statement
          notes
          sfxIds
          universe
          dice
          spentDice
          capacity
          polarity
          enabled
          traitsetOrder
          traitsetLimit
          knownTo
          possibleSfxIds
        tags
          relationshipContactId
          relationshipContactName
          relationshipContactType
          relationshipType
          possibleSubtraitIds
        }
      }
    }
  `
  const data = await graphql(query, {
    viewer: props.viewerEntityId,
    target: props.overrideEntityId,
  })
  relationship.value = data?.relationship || null
}

async function saveRelationship() {
  if (!props.viewerEntityId || !props.overrideEntityId) return
  const query = `
    mutation($from: ID!, $to: ID!, $desc: String!) {
      createRelationship(input: { fromEntityId: $from, toEntityId: $to, description: $desc }) {
        description
      }
    }
  `
  await graphql(query, {
    from: props.viewerEntityId,
    to: props.overrideEntityId,
    desc: relDescription.value,
  })
  showRelEditor.value = false
  await fetchRelationship()
}

async function createImmediateRelationship() {
  if (!props.viewerEntityId || !props.overrideEntityId) return
  const query = `
    mutation($from: ID!, $to: ID!) {
      createRelationship(input: { fromEntityId: $from, toEntityId: $to }) {
        description
      }
    }
  `
  await graphql(query, {
    from: props.viewerEntityId,
    to: props.overrideEntityId,
  })
  await fetchRelationship()
}

function openBlueBookLetter() {
  activeSheetView.value = 'bluebook'
  nextTick(() => {
    blueBookRef.value?.openCompose('new', {
      id: props.overrideEntityId || props.entityId,
      name: entity.value?.name || ''
    })
  })
}

async function removeRelationship() {
  if (!props.viewerEntityId || !props.overrideEntityId) return
  const query = `
    mutation($from: ID!, $to: ID!) {
      deleteRelationship(input: { fromEntityId: $from, toEntityId: $to })
    }
  `
  await graphql(query, {
    from: props.viewerEntityId,
    to: props.overrideEntityId,
  })
  relationship.value = null
  showRelEditor.value = false
}

watch(() => props.overrideEntityId, () => {
  if (isForeignSheet.value) fetchRelationship()
  if (!ownsCharacter.value && activeSheetView.value === 'bluebook') activeSheetView.value = 'traits'
  // The relation view belongs to one specific edge — don't carry it across sheets.
  if (activeSheetView.value === 'relation') activeSheetView.value = 'traits'
})
watch(() => props.viewerEntityId, () => {
  if (isForeignSheet.value) fetchRelationship()
})

// Sync external pool sources (for GM panel)
watch(() => props.externalPoolSources, (sources) => {
  if (sources !== null) poolSources.value = [...sources]
}, { immediate: true })
</script>

<style scoped>
.sheet-embedded {
  background: var(--bg-panel);
  backdrop-filter: blur(12px);
  border-radius: var(--radius);
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  position: relative;
  min-height: 0;
}

/* Transparent (background-removed) sheet portraits: no circular crop — the
   character cutout pops out over the sheet's top edge. Bottom-only border +
   radius anchor it to the sheet; the top stays open and uncropped. */
.sheet-embedded.transparent-portrait {
  --portrait-size: 76px;
  --portrait-lift: 34px;
  --portrait-bottom-radius: 14px;
}
.sheet-embedded.transparent-portrait .header-top,
.sheet-embedded.transparent-portrait .header-controls {
  padding-right: calc(var(--portrait-size) + 8px);
}
.sheet-portrait.transparent {
  width: var(--portrait-size);
  height: auto;
  object-fit: contain;
  position: absolute;
  top: calc(-1 * var(--portrait-lift));
  right: 16px;
  border: none;
  border-bottom: 1px solid var(--overlay-12);
  border-radius: 0 0 var(--portrait-bottom-radius) var(--portrait-bottom-radius);
}

.sheet-scroll {
  flex: 1;
  overflow-y: auto; overflow-x: hidden;
}

.set-header {
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 8px 0 4px;
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-dim);
  transition: color 0.15s;
}
.set-header:hover {
  color: var(--text);
}
.trait-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.trait-list-title {
  align-self: flex-start;
  cursor: pointer;
  user-select: none;
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text);
  transition: color 0.15s;
}
.trait-list-title:hover {
  color: var(--accent);
}
.trait-list-wrap {
  flex-direction: row;
  flex-wrap: wrap;
  gap: 6px;
}
.trait-list-wrap .trait-row {
  margin: 0;
  flex: 0 0 auto;
  max-width: 100%;
  background: var(--overlay-2);
}
.trait-list-wrap .trait-left {
  flex: 0 1 auto;
}
  .set-back { align-self: flex-start;
    margin-bottom: 6px; }
  .next-set-btn { align-self: flex-end;
    margin-top: 6px; }

.limit-dots {
  font-size: 10px;
  margin-left: auto;
  letter-spacing: 1px;
  vertical-align: middle;
  flex-shrink: 0;
}
.limit-dot {
  opacity: 0.35;
  transition: opacity 0.15s;
}
.limit-dot.filled {
  opacity: 1;
  color: var(--accent);
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

.trait-edit-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 4px 0 8px;
}
.edit-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.edit-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.6px;
}
.edit-flags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
}
.edit-title {
  margin: 0 0 2px;
  font-size: 14px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text);
}
.edit-dice {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.edit-dice .die-chip {
  font-size: 14px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 6px;
  border: 2px solid var(--overlay-10);
  background: var(--overlay-6);
  color: var(--text);
  cursor: pointer;
  transition: border-color 0.15s;
}
.edit-dice .die-chip:hover {
  border-color: var(--accent);
}
.edit-dice .add-chip {
  color: var(--accent);
  border-color: var(--accent-dim);
  font-size: 16px;
  font-weight: 400;
  padding: 3px 8px;
}
.edit-dice .add-chip:hover {
  border-color: var(--accent);
  background: var(--accent-12);
}
.edit-spent-dice {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.edit-spent-label {
  font-size: 12px;
  color: var(--text-dim);
}
.edit-spent-dice .die-chip {
  font-size: 13px;
  font-weight: 700;
  padding: 2px 9px;
  border-radius: 6px;
  border: 2px dashed var(--overlay-25);
  background: var(--overlay-4);
  color: var(--text-dim);
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}
.edit-spent-dice .die-chip:hover {
  border-color: var(--accent);
  color: var(--text);
}
.edit-dice .die-chip.die-chip-icon,
.edit-spent-dice .die-chip.die-chip-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  line-height: 0;
}
.edit-dice .die-chip.die-chip-icon .die-icon,
.edit-spent-dice .die-chip.die-chip-icon .die-icon {
  width: 28px;
  height: 30px;
}
.edit-spent-dice .die-chip.die-chip-icon .die-icon {
  opacity: 0.45;
}
.edit-rating-type {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
}
.rating-type-btn {
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--overlay-12);
  background: transparent;
  color: var(--text-dim);
  font-size: 11px;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}
.rating-type-btn.active {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-12);
}
.edit-sfx {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}
.sfx-chip {
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid var(--overlay-10);
  background: var(--overlay-4);
  color: var(--text-dim);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.sfx-chip:hover {
  border-color: var(--overlay-20);
  color: var(--text);
}
.sfx-chip.assigned {
  background: var(--accent-dim);
  border-color: var(--accent);
  color: var(--accent);
}

.edit-subtraits {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.edit-subtrait-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid var(--overlay-10);
  background: var(--overlay-4);
}
.edit-subtrait-name { font-weight: 500; }
.edit-subtrait-statement { font-size: 11px; opacity: 0.7; flex: 1; }
  .edit-subtrait-remove { margin-left: auto;
    flex-shrink: 0; }
.edit-subtraits-add {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  margin-top: 4px;
}
.edit-subtrait-add-label { font-size: 11px; color: var(--text-dim); }
.edit-subtrait-chip {
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid var(--overlay-10);
  background: var(--overlay-4);
  color: var(--text-dim);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.edit-subtrait-chip:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.edit-subtrait-empty { font-size: 11px; color: var(--text-dim); }

.edit-statement,
.edit-notes {
  width: 100%;
  box-sizing: border-box;
  background: var(--overlay-4);
  border: 1px solid var(--overlay-12);
  border-radius: 6px;
  color: var(--text);
  font-size: 12px;
  font-family: inherit;
  padding: 6px 8px;
  transition: border-color 0.15s;
}
.edit-statement:focus,
.edit-notes:focus {
  outline: none;
  border-color: var(--accent-dim);
}
.edit-notes {
  min-height: 56px;
  resize: vertical;
}
.edit-actions {
  display: flex;
  gap: 6px;
  margin-top: 4px;
  padding-top: 12px;
  border-top: 1px solid var(--overlay-8);
}
  .edit-done-btn { flex: 1; }
  .edit-delete-btn { flex: 1; }

  .add-trait-btn { margin-top: 8px; }

.trait-picker {
  margin-top: 8px;
  padding: 8px 0;
  max-height: calc(100vh - 320px);
  overflow-y: auto; overflow-x: hidden;
}
.trait-picker h4 {
  font-size: 12px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 6px;
}
.picker-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 6px 10px;
  font-size: 13px;
  background: var(--overlay-4);
  border: 1px solid var(--overlay-6);
  border-radius: 6px;
  color: var(--text);
  cursor: pointer;
  margin-bottom: 4px;
  transition: background 0.15s, border-color 0.15s;
}
.picker-item:hover {
  background: var(--overlay-8);
  border-color: var(--overlay-12);
}
.picker-die {
  font-weight: 700;
  font-size: 12px;
  color: var(--text-dim);
}
  .picker-back { margin-bottom: 6px; }
  .picker-cancel { margin-top: 6px; }

.header-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.header-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  flex-wrap: wrap;
}
.sheet-portrait {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  object-fit: cover;
  border: 1px solid var(--overlay-12);
  flex-shrink: 0;
  order: 1;
}
.sheet-portrait-video {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  object-fit: cover;
  border: 1px solid var(--overlay-12);
  flex-shrink: 0;
  order: 1;
}
.header-top h2 {
  flex: 1;
}

.header {
  margin-bottom: 16px;
}
.header h2 {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 4px;
}
/* Title + projection name. The character name stays the title until the body
   is named; then the body name takes the title and the character name shrinks
   to an overline above it. */
.header-title { flex: 1; min-width: 0; }
.header-title h2 { margin-bottom: 2px; }
.name-overline {
  font-size: 11px;
  line-height: 1.3;
  margin-bottom: 1px;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.name-primary { font-size: 20px; font-weight: 700; }
.name-secondary { display: flex; align-items: center; min-height: 17px; }
/* These overrides must beat the primitive's .btn-md/.btn-link rules from the
   child stylesheet, hence the .header-title descendant prefix. */
.header-title .name-primary-btn {
  padding: 0;
  font-size: 20px;
  font-weight: 700;
  line-height: 1.2;
  text-align: left;
  color: var(--text);
}
.header-title .projection-name-btn { padding: 0; font-size: 12px; font-weight: 400; }
.header-title .projection-name-btn.unset { color: var(--text-dim); }
.header-title .projection-name-btn.unset:hover { color: var(--accent); }
.projection-name-input {
  font: inherit;
  font-size: 12px;
  color: var(--text);
  background: var(--overlay-8);
  border: 1px solid var(--accent);
  border-radius: 4px;
  padding: 1px 6px;
  width: 100%;
  max-width: 220px;
}
.projection-name-input.is-primary { font-size: 20px; font-weight: 700; padding: 2px 8px; }
.meta {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: var(--text-dim);
}
.universe {
  text-transform: uppercase;
  letter-spacing: 1px;
}
.active-effects {
  color: var(--accent, #d9b45a);
  font-size: 11px;
}
.ego-toggle {
  padding: 3px 12px;
  border-radius: 999px;
  border: 1px solid var(--text-dim);
  background: transparent;
  color: var(--text-dim);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  cursor: pointer;
}
.ego-toggle.is-ego {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--overlay-6);
}
.polarity-toggle {
  padding: 3px 12px;
  border-radius: 999px;
  border: 1px solid var(--text-dim);
  background: transparent;
  color: var(--text-dim);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  cursor: pointer;
}
.polarity-toggle.is-positive {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--overlay-6);
}
.edit-projection {
  display: flex;
  align-items: center;
  gap: 6px;
  position: relative;
}
.edit-projection-label {
  font-size: 10px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.projection-chip {
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid var(--accent-dim);
  background: var(--accent-12);
  color: var(--accent);
  font-size: 11px;
  cursor: pointer;
}
.projection-chip:hover {
  border-color: var(--accent);
}
.projection-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  z-index: 20;
  margin-top: 4px;
  min-width: 160px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.4);
  overflow: hidden;
}
.projection-option {
  display: block;
  width: 100%;
  padding: 6px 10px;
  background: transparent;
  border: none;
  color: var(--text);
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}
.projection-option:hover {
  background: var(--bg-hover);
}
.projection-option.selected {
  color: var(--accent);
  background: var(--accent-12);
}
.razmerit-anchor {
  position: relative;
  flex-shrink: 0;
}
.razmerit-chip {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  background: transparent;
  border: 1px solid var(--overlay-12);
  border-radius: 999px;
  padding: 5px 10px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.razmerit-chip:hover {
  border-color: var(--accent-dim);
  background: var(--accent-8);
}
.razmerit-popover {
  position: absolute;
  top: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  z-index: 30;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg-panel);
  border: 1px solid var(--overlay-12);
  border-radius: 10px;
  box-shadow: 0 6px 20px rgba(0,0,0,0.4);
  white-space: nowrap;
}
.razmerit-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--accent);
}
.razmerit-value.editable {
  cursor: pointer;
}
.razmerit-input {
  width: 64px;
  font-size: 24px;
  font-weight: 700;
  color: var(--accent);
  background: var(--overlay-4);
  border: 1px solid var(--accent-dim);
  border-radius: 6px;
  padding: 2px 4px;
  text-align: center;
}

.trait-sets {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.trait-set h4 {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 2px;
  color: var(--text-dim);
  margin-bottom: 6px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--overlay-6);
}

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
.trait-row:hover {
  background: var(--overlay-4);
}
.trait-row.morph {
  background: var(--accent-8);
  border-left: 2px solid var(--accent);
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
.trait-disabled-badge {
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-dim);
  margin-left: 6px;
  padding: 1px 5px;
  border: 1px solid var(--text-dim);
  border-radius: 999px;
  white-space: nowrap;
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

.trait-die {
  font-weight: 700;
  font-size: 14px;
}
.die-d4  { color: var(--die-d4); }
.die-d6  { color: var(--die-d6); }
.die-d8  { color: var(--die-d8); }
.die-d10 { color: var(--die-d10); }
.die-d12 { color: var(--die-d12); }

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
.trait-die.depleted {
  color: var(--text-dim);
  font-style: italic;
}
.challenge-progress {
  align-self: center;
  font-size: 12px;
  color: var(--text-dim);
  white-space: nowrap;
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

.loading, .error, .empty {
  font-size: 13px;
  color: var(--text-dim);
  text-align: center;
  padding: 16px 0;
}
.error { color: var(--danger); }
.empty-no-entity {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.sfx-cards {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
}
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

.entity-sfx-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 4px 0;
}

/* ── Relationship widget ──────────────────────── */
.rel-widget {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 4px;
  position: relative;
  flex-shrink: 0;
}
.rel-desc {
  font-size: 11px;
  color: var(--text-dim);
  font-style: italic;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  transition: color 0.15s, background 0.15s;
}
.rel-desc:hover {
  color: var(--text);
  background: var(--bg-hover);
}
.rel-editor {
  position: absolute;
  top: 100%;
  left: 0;
  z-index: 10;
  display: flex;
  gap: 4px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.4);
}
.rel-editor input {
  width: 180px;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-input);
  color: var(--text);
  font-size: 12px;
  font-style: italic;
  outline: none;
}
.rel-editor input:focus {
  border-color: var(--accent);
}
.sheet-pills { display: flex; gap: 0; margin-bottom: 10px; border-radius: 20px; overflow: hidden; border: 1px solid var(--overlay-8); }
.pill { padding: 5px 14px; font-size: 11px; border: none; cursor: pointer; background: var(--overlay-2); color: var(--text-dim); transition: background 0.15s, color 0.15s; }
.pill + .pill { border-left: 1px solid var(--overlay-6); }
.pill:hover { background: var(--overlay-4); color: var(--text); }
.pill.active { background: var(--accent-dim); color: var(--text); font-weight: 600; }
/* ── Trait detail (read-only) ────────────────────────
   A drill-in that replaces the trait list. Layout priority top-down: the
   mechanical cores (rating, SFX) above the narrative tail. */
.trait-detail-panel { display: flex; flex-direction: column; }

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}
/* Descendant-prefixed so these beat the primitive's .btn-md/.btn-link rules. */
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

/* The rating band is the play target, mirroring the trait row's rating zone. */
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

/* Rendered only when it has rows, so a plain static trait ends at Notes. */
.detail-context { display: flex; flex-direction: column; gap: 2px; }
.detail-context-row { display: flex; gap: 10px; font-size: 11px; }
.detail-context-label { min-width: 68px; color: var(--text-dim); }
.detail-context-value { color: var(--text); }

.detail-text { margin: 0; font-size: 12px; line-height: 1.5; color: var(--text); white-space: pre-wrap; }

/* The derived natural-language rules line inside a detail SFX card. Brighter
   than the flavour lead-in above it — this is the text that tells you what the
   SFX actually does. */
.detail-section .sfx-card-rules {
  margin-top: 2px;
  font-size: 11px;
  line-height: 1.35;
  color: var(--text);
}
</style>
