<template>
  <!-- Embedded: single root for attribute inheritance -->
  <div v-if="embedded" class="sheet-embedded" :class="{ 'transparent-portrait': sheetPortraitTransparent }">
    <!-- The loading/error placeholders are gated on `!hasEntity`, not on
         `loading` alone. `useApi()`'s `loading` ref is set by *every* call, so a
         plain `v-if="loading"` swaps this branch out during each background
         refresh — and a `v-if` branch key is its index, so swapping back
         unmounts and remounts the entire entity subtree (B125). Once an entity
         is in hand the sheet stays mounted and refreshes in place. -->
    <div v-if="!hasEntity && loading" class="loading">Loading…</div>
    <div v-else-if="!hasEntity && error" class="error">{{ error }}</div>
    <template v-else-if="hasEntity">
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
          <div v-if="sheetProfile.razmerit" class="razmerit-anchor">
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
          <MediaImage
            v-if="sheetPortrait"
            :src="sheetPortrait"
            class="sheet-portrait clickable"
            :class="{ transparent: sheetPortraitTransparent }"
            aria-role="button"
            tabindex="0"
            :aria-label="`View ${entity.name}'s full image`"
            title="View full image"
            @click.stop="portraitViewerOpen = true"
            @keydown.enter.prevent="portraitViewerOpen = true"
            @keydown.space.prevent="portraitViewerOpen = true"
          />
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
                <button v-if="hasTab('profile')" :class="['pill', { active: activeSheetView === 'profile' }]" @click="activeSheetView = 'profile'">👤</button>
                <button v-if="hasTab('traits')" :class="['pill', { active: activeSheetView === 'traits' }]" @click="goToTraitSets">🎲</button>
                <button v-if="gmMode" :class="['pill', { active: showAllTraits }]" :title="showAllTraits ? 'Showing all traits' : 'Show all traits'" @click="showAllTraits = !showAllTraits">🌍</button>
                <button v-if="hasTab('roster')" :class="['pill', { active: activeSheetView === 'roster' }]" :title="`Members of ${entity.name}`" @click="activeSheetView = 'roster'">👥</button>
                <button v-if="showTiesTab" :class="['pill', { active: activeSheetView === 'ties' }]" :title="`What others hold about ${entity.name}`" @click="activeSheetView = 'ties'">🔗</button>
                <button v-if="hasTab('bluebook')" :class="['pill', { active: activeSheetView === 'bluebook' }]" @click="activeSheetView = 'bluebook'">📘</button>
                <button v-if="hasTab('lifepath')" :class="['pill', { active: activeSheetView === 'lifepath' }]" @click="activeSheetView = 'lifepath'">🛤️</button>
              </template>
            </div>
            <Button v-if="!gmMode && !isForeignSheet" variant="ghost" size="icon" title="Player settings" @click.stop="$emit('openSettings')">↩</Button>
            <!-- This tie runs from `viewerEntityId` (who you are acting as) to the
                 entity you are viewing, so it needs someone to be acting as. A
                 roaming GM has no acting entity, which is the one case where the
                 one-click would be dead — `createImmediateRelationship` returns
                 early. A GM *acting as* an entity still gets it: the tie belongs to
                 that entity, not to the GM. -->
            <Button v-if="isForeignSheet && !relationship && viewerEntityId" variant="ghost" size="icon" title="Add relationship" @click.stop="createImmediateRelationship()">+</Button>
          </div>
        </div>
        <div v-if="entitySfxIds.length || projectionSfxIds.length || entityGrantedSfxIds.length || projectionGrantedSfxIds.length" class="entity-sfx-cards">
          <SfxCard v-for="sfxId in entitySfxIds" :key="'e-' + sfxId" v-bind="sfxCardModel(sfxId)"
                   @activate="activateSfx(sfxId, entity.id)" />
          <!-- Granted to the *entity* rather than attached: read-time, so there is
               nothing here to detach, and the rule can stop applying when the world
               changes (a GMC that stops being hidden, say). `sfx-reveal-entity` is
               the live example — it reaches every hidden GMC and, before this, was
               available and drawn nowhere. -->
          <SfxCard
            v-for="sfxId in entityGrantedSfxIds"
            :key="'eg-' + sfxId"
            class="sfx-granted"
            v-bind="sfxCardModel(sfxId)"
            @activate="activateSfx(sfxId, entity.id)"
          />
          <SfxCard v-for="sfxId in projectionSfxIds" :key="'p-' + sfxId" v-bind="sfxCardModel(sfxId)"
                   @activate="activateSfx(sfxId, activeProjection.id)" />
          <!-- The same, for the body: a projection is one of the four owner kinds a
               granted declaration can select. -->
          <SfxCard
            v-for="sfxId in projectionGrantedSfxIds"
            :key="'pg-' + sfxId"
            class="sfx-granted"
            v-bind="sfxCardModel(sfxId)"
            @activate="activateSfx(sfxId, activeProjection.id)"
          />
        </div>
        <!-- Rules lent by the place you are standing in. Not attached to you:
             they reach you because you're here, and leave when you do. -->
        <div v-if="placeRuleGroups.length" class="place-sfx-rules">
          <div v-for="g in placeRuleGroups" :key="g.locationId" class="place-sfx-group">
            <span class="place-sfx-label">From {{ g.locationName }}</span>
            <div class="entity-sfx-cards">
              <SfxCard v-for="sfxId in g.sfxIds" :key="g.locationId + ':' + sfxId"
                       v-bind="placeCardModel(sfxId)"
                       @activate="activateSfx(sfxId, g.locationId)" />
            </div>
          </div>
        </div>
        <div v-if="gmMode" class="meta">
          <span class="location">{{ locationName || entity.currentLocation || 'Unknown' }}</span>
          <span class="universe">{{ universeName || entity.currentUniverse }}</span>
          <span v-if="entityTimerLabel" class="active-effects" :title="'Timed effects pending: ' + entityTimerLabel">⏳ {{ entityTimerLabel }}</span>
        </div>
      </div>
      <!-- A choice raised *from this sheet* is answered **as this sheet's body**,
           not floated over it. It takes the same slot every other sheet view
           takes, so it reads like the life path's choice table in this same
           panel instead of a card lying over the trait that raised the question
           — which was both unreadable (its own background is `--overlay-2`, ~2%
           opaque) and a lie about what the click did. `embedded` removes the
           wizard's own card for the same reason: the panel is the container. -->
      <div v-if="sfxChoiceRequest && sfxChoiceRequest.length" class="sheet-sfx-choice">
        <EffectTargetWizard
          :entity-id="entityId"
          :pending-choices="sfxChoiceRequest"
          title="Choose a target"
          embedded
          @resolve="onChoiceResolved"
          @cancel="emit('sfx-choice-cancel')"
          @run-loop="(c) => emit('sfx-choice-loop', c)"
        />
      </div>
      <!-- The roll table a menu rule opened: the same slot as the question above,
           because the panel is the container. It used to be teleported to `<body>`
           and floated over the whole screen — which was also the reason it read as
           "not in the sheet". -->
      <div v-else-if="rollTableMenu" class="sheet-sfx-choice sheet-roll-table">
        <RollTableMenu
          embedded
          :entity-id="sfxSubjectId"
          :table-id="rollTableMenu.tableId"
          :title="rollTableMenu.name"
          :entity-razmerit="entity?.razmerit ?? 0"
          :mode="rollTableMenu.mode || 'apply'"
          :player-id="playerId"
          :main-entity-id="mainEntityId"
          @close="rollTableMenu = null"
        />
      </div>
      <BlueBook
        v-else-if="activeSheetView === 'bluebook'"
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
      <!-- Faction roster — a faction's members, which live on `membership`
           edges and read through `factionMembers`. A row is a control: it asks
           the app to bring that member's sheet up, which is the same "view this
           entity" action a peer chip performs — so the app's existing grammar
           decides what a second click means, and nothing new is invented here. -->
      <div v-else-if="activeSheetView === 'roster'" class="sheet-scroll">
        <div v-if="rosterLoading" class="empty">Loading roster…</div>
        <div v-else-if="!roster.length" class="empty">No members recorded</div>
        <template v-else>
          <h4 class="roster-title">{{ roster.length }} member{{ roster.length === 1 ? '' : 's' }}</h4>
          <div class="roster-list">
            <div
              v-for="m in roster"
              :key="m.id"
              class="roster-row"
              role="button"
              tabindex="0"
              :aria-label="`View ${m.name}'s sheet`"
              :title="`View ${displayName(m.name)}`"
              @click="emit('viewEntity', m.id)"
              @keydown.enter.prevent="emit('viewEntity', m.id)"
              @keydown.space.prevent="emit('viewEntity', m.id)"
            >
              <span class="roster-name">{{ displayName(m.name) }}</span>
              <span class="roster-type">{{ memberTypeBadge(m.type) }}</span>
              <span class="roster-role" :class="{ unset: !m.role }">{{ m.role || 'no role' }}</span>
              <span v-if="m.rank" class="roster-rank" :title="'Rank die'">{{ m.rank }}</span>
            </div>
          </div>
        </template>
      </div>
      <!-- Incoming ties (B134) — the mirror of the relation tab: not what we
           hold about this entity but what everyone else does. Grouped by the
           holder, because that is the question ("who is tied to this place"),
           and each tie's traits render as ordinary rows so a tie's die,
           statement and detail panel read exactly as they do anywhere else. -->
      <div v-else-if="activeSheetView === 'ties'" class="sheet-scroll">
        <div v-if="incomingTiesLoading" class="empty">Loading ties…</div>
        <div v-else-if="!incomingTies.length" class="empty">Nobody holds a tie here</div>
        <template v-else>
          <h4 class="ties-title">{{ incomingTies.length }} tie{{ incomingTies.length === 1 ? '' : 's' }} held about {{ entity.name }}</h4>
          <div class="ties-list">
            <div v-for="tie in incomingTies" :key="tie.edgeId" class="tie-group">
              <div
                class="tie-holder"
                role="button"
                tabindex="0"
                :aria-label="`View ${tie.holderName}'s sheet`"
                :title="`View ${displayName(tie.holderName)}`"
                @click="emit('viewEntity', tie.holderId)"
                @keydown.enter.prevent="emit('viewEntity', tie.holderId)"
                @keydown.space.prevent="emit('viewEntity', tie.holderId)"
              >
                <span class="tie-name">{{ displayName(tie.holderName) }}</span>
                <span class="roster-type">{{ memberTypeBadge(tie.holderType) }}</span>
                <span v-if="tie.description" class="tie-desc">{{ tie.description }}</span>
              </div>
              <div v-if="tie.traits.length" class="tie-traits">
                <TraitRow
                  v-for="t in tie.traits"
                  :key="t.id"
                  :trait="t"
                  :api="traitRowApi"
                  :phase="phase"
                />
              </div>
            </div>
          </div>
        </template>
      </div>
      <template v-else>
        <div class="sheet-scroll">
        <!-- Full-panel trait edit -->
        <TraitEditPanel
          v-if="editingTrait && !showAddTrait"
          :trait="editingTrait"
          :dice="editDice"
          :capacity="editCapacity"
          :rating-type="editRatingType"
          :polarity="editPolarity"
          :statement="editStatement"
          :notes="editNotes"
          :sfx-ids="editSfxIds"
          :acquirable-sfx-ids="acquirableSfxIds"
          :tags="editTags"
          :inherit-tags="editingTrait?.registryTags || []"
          :tag-suggestions="tagSuggestions"
          :is-ego="editIsEgo"
          :projection-id="editProjectionId"
          :projection-name="editProjectionName"
          :projection-options="projectionChoices"
          :subtraits="availableSubtraits"
          :show-projection-picker="showProjectionPicker"
          :delete-countdown="deleteCountdown"
          :deleting-trait-id="deletingTraitId"
          :definition-options="definitionOptions"
          :can-redeclare="editingTrait?.fromType !== 'relationship'"
          :definition-pending="definitionPending"
          :show-definition-picker="showDefinitionPicker"
          :definition-filter="definitionFilter"
          :definition-traitsets="definitionTraitsets"
          :definition-traitset-filter="definitionTraitsetFilter"
          @update:dice="editDice = $event"
          @update:capacity="editCapacity = $event"
          @update:statement="editStatement = $event"
          @update:notes="editNotes = $event"
          @update:tags="editTags = $event"
          @rating-type="onEditorRatingType"
          @change="onEditorChange"
          @field-blur="onEditorFieldBlur"
          @recover-die="recoverSpentDie"
          @back="cancelEdit"
          @delete="onDeleteClick"
          @toggle-sfx="toggleSfx"
          @toggle-ego="toggleEgo"
          @toggle-polarity="togglePolarity"
          @toggle-projection-picker="toggleProjectionPicker"
          @select-projection="selectProjection"
          @add-subtrait="addSubTrait"
          @remove-subtrait="removeSubTrait"
          @toggle-definition-picker="toggleDefinitionPicker"
          @update:definitionFilter="definitionFilter = $event"
          @update:definitionTraitsetFilter="definitionTraitsetFilter = $event"
          @change-definition="changeDefinition"
          @image-changed="fetchEntity('trait-image')"
        />

        <!-- Trait detail (read-only) — the row's "elsewhere" click zone.
             Right-click on the row, or the header's Edit, opens the editor. -->
        <TraitDetailPanel
          v-else-if="detailTrait && !showAddTrait"
          :trait="detailTrait"
          :api="detailApi"
          @back="closeTraitDetail"
          @edit="startEdit"
        />

        <!-- Traits tab: trait-set list. Skipped entirely on a low-trait sheet
             (B60) — the list below then shows every set's traits at once. The
             two things that live only here and are therefore absent flat: a
             set's limit dots and its trait-set-unit SFX cards (0 rows in the
             live data carry the latter — flagged, not yet designed).

             Two shapes, by the sheet's height (the human's rule, 2026-09-25):
             the **accordion** where there is height to spare — a landscape
             desktop or tablet, several sets open at once — and the **drill-in**
             everywhere else, where the set list is navigation and one set's
             traits replace it. -->
        <div v-else-if="activeSheetView === 'traits' && !flatTraitList && traitSetAccordion && traitSets.length && !showAddTrait" class="trait-sets">
          <div v-for="entry in accordionSets" :key="entry.ts.name" class="trait-set" :class="{ open: isSetOpen(entry.ts.name) }">
            <h4 class="set-header">
              <button
                class="set-toggle"
                :aria-expanded="isSetOpen(entry.ts.name) ? 'true' : 'false'"
                @click="toggleSet(entry.ts.name)"
              >
                <span class="set-chevron">{{ isSetOpen(entry.ts.name) ? '▾' : '▸' }}</span>
                <span class="set-name">{{ entry.ts.name }}</span>
              </button>
              <span v-if="entry.ts.limit" class="limit-dots">
                <span v-for="i in entry.ts.limit" :key="i" class="limit-dot" :class="{ filled: i <= inPoolCount(entry.ts) }">{{ i <= inPoolCount(entry.ts) ? '●' : '○' }}</span>
              </span>
              <!-- Only on an open set: a collapsed row is a line you scan, and a
                   second control on it competes with the toggle for the tap. -->
              <button
                v-if="canAddTraits && isSetOpen(entry.ts.name)"
                class="set-add"
                :title="`Add a ${entry.ts.name} trait`"
                :aria-label="`Add a ${entry.ts.name} trait`"
                @click="openAddTrait(entry.ts)"
              >＋</button>
            </h4>
            <!-- The set's own rules sit **inside the set**: first under its title,
                 above the rows (the human's call, 2026-09-29), and now *only while
                 the set is open* (2026-09-29, their follow-up). A set-as-a-unit rule
                 is a fact about the set, so it belongs to the set's contents — a
                 collapsed set is a line you scan, and a card hanging under it was
                 the one thing that did not disappear with it. -->
            <div
              v-if="isSetOpen(entry.ts.name) && (traitsetSfxIds(entry.ts).length || traitsetGrantedSfxIds(entry.ts).length)"
              class="sfx-cards"
            >
              <SfxCard v-for="sfxId in traitsetSfxIds(entry.ts)" :key="'ts-' + sfxId" v-bind="sfxCardModel(sfxId)"
                       @activate="activateSfx(sfxId, traitsetSettingSourceId(entry.ts))" />
              <!-- Granted to the set as a unit rather than attached to it. -->
              <SfxCard
                v-for="sfxId in traitsetGrantedSfxIds(entry.ts)"
                :key="'tsg-' + sfxId"
                class="sfx-granted"
                v-bind="sfxCardModel(sfxId)"
                @activate="activateSfx(sfxId, traitsetSettingSourceId(entry.ts))"
              />
            </div>
            <div v-if="isSetOpen(entry.ts.name)" class="set-traits">
              <TraitRow
                v-for="t in entry.traits"
                :key="t.id"
                :trait="t"
                :api="traitRowApi"
                :phase="phase"
                :limit-reached="limitReachedFor(t)"
                :hide-contact="entry.continuations.has(t.id)"
              />
            </div>
          </div>
        </div>

        <!-- The drill-in's first phase: the sets as navigation, shown only until
             one is entered. No `[+]` here — a set you hold nothing in is reached
             through `+ Add Trait` below, which is the pre-accordion path and
             still the only one that can add to a set the list has no entry for.
             And no set-level rules either (2026-09-29): this list is navigation, so
             a set's rules belong to the set **entered**, which is where the detail
             branch below draws them. They used to show here too, which meant a rule
             for every set at once on the one screen where you have entered none. -->
        <div v-else-if="activeSheetView === 'traits' && !flatTraitList && !drilledSet && traitSets.length && !showAddTrait" class="trait-sets">
          <div v-for="ts in traitSets" :key="ts.name" class="trait-set">
            <h4 class="set-header set-header-link" @click="openSet(ts.name)">
              <span class="set-chevron">▸</span>
              <span class="set-name">{{ ts.name }}</span>
              <span v-if="ts.limit" class="limit-dots">
                <span v-for="i in ts.limit" :key="i" class="limit-dot" :class="{ filled: i <= inPoolCount(ts) }">{{ i <= inPoolCount(ts) ? '●' : '○' }}</span>
              </span>
            </h4>
          </div>
        </div>

        <!-- The whole-sheet flat list (B60), the profile tab, the relation tab, or
             the set the reader drilled into. A sheet with few traits keeps the flat
             list: the sets are a navigation device and with a handful of traits
             there is nothing to navigate, so the two are the same list with and
             without the set layer rather than a choice. -->
        <div v-else-if="currentTraits.length && !showAddTrait" class="trait-list" :class="{ 'trait-list-wrap': activeSheetView === 'profile' }">
            <h4
              v-if="activeSheetView === 'traits' && !flatTraitList"
              class="trait-list-title"
              @click="closeSet"
              title="Back to trait sets"
            >← {{ drilledSet?.name }}</h4>
            <!-- The entered set's own rules, in the same place the accordion puts
                 them: under the set's title, above its rows. Without this the
                 drill-in — which is the default everywhere there is no height to
                 spare, so phones and portrait tablets — never drew a set-level
                 rule at all. -->
            <div
              v-if="drilledSet && (traitsetSfxIds(drilledSet).length || traitsetGrantedSfxIds(drilledSet).length)"
              class="sfx-cards"
            >
              <SfxCard v-for="sfxId in traitsetSfxIds(drilledSet)" :key="'ts-' + sfxId" v-bind="sfxCardModel(sfxId)"
                       @activate="activateSfx(sfxId, traitsetSettingSourceId(drilledSet))" />
              <SfxCard
                v-for="sfxId in traitsetGrantedSfxIds(drilledSet)"
                :key="'tsg-' + sfxId"
                class="sfx-granted"
                v-bind="sfxCardModel(sfxId)"
                @activate="activateSfx(sfxId, traitsetSettingSourceId(drilledSet))"
              />
            </div>
            <TraitRow
              v-for="t in currentTraits"
              :key="t.id"
              :trait="t"
              :api="traitRowApi"
              :phase="phase"
              :limit-reached="limitReachedFor(t)"
              :wrap="activeSheetView === 'profile'"
              :hide-contact="traitContinuations.has(t.id)"
              :show-notes="activeSheetView === 'profile'"
            />
          <!-- The set order, so a reader can walk a sheet's sets without going back
               to the list each time. `align-self: stretch` on the row is what lets a
               lone Prev sit left and a lone Next right. -->
          <div v-if="activeSheetView === 'traits' && !flatTraitList && (prevSet || nextSet)" class="set-nav">
            <Button v-if="prevSet" class="set-nav-prev" variant="neutral" @click="goToPrevSet">← Previous: {{ prevSet.name }}</Button>
            <Button v-if="nextSet" class="set-nav-next" variant="neutral" @click="goToNextSet">Next: {{ nextSet.name }} →</Button>
          </div>
        </div> <!-- .trait-list -->
      <div v-else-if="!showAddTrait" class="empty">{{ activeSheetView === 'profile' ? 'No profile traits' : 'No traits configured' }}</div>
      <Button v-if="canAddTraits && !showAddTrait" class="add-trait-btn" variant="secondary" block @click="openAddTrait">+ Add Trait</Button>
      <Button v-if="isForeignSheet && !showAddTrait" class="add-trait-btn" variant="secondary" block @click="openAddRelationshipTrait">+ Add relationship trait</Button>
      <!-- 2-phase trait picker -->
      <div v-if="showAddTrait" class="trait-picker">
        <template v-if="addPhase === 'sets'">
          <h4>Pick a trait set</h4>
          <button v-for="ts in availableTraitSets" :key="ts.id" class="picker-item" @click="selectSet(ts)">{{ ts.name }}</button>
        </template>
        <template v-if="addPhase === 'relationships'">
          <Button class="picker-back" variant="link" @click="addPhase = 'sets'">← {{ selectedTraitSet?.name }}</Button>
          <h4>Which relationship?</h4>
          <input
            v-model="relationshipFilter"
            class="picker-filter"
            type="search"
            placeholder="Filter relationships…"
            aria-label="Filter relationships"
          />
          <button v-for="c in filteredRelationships" :key="c.id" class="picker-item" @click="selectRelationship(c)">
            {{ displayName(c.name) }}
            <span class="picker-type">{{ c.bucket }}</span>
          </button>
          <div v-if="relationshipsLoading" class="empty">Loading relationships…</div>
          <div v-else-if="!relationships.length" class="empty">
            No relationships yet — add one from the other character’s sheet.
          </div>
          <div v-else-if="!filteredRelationships.length" class="empty">No relationship matches.</div>
        </template>
        <template v-if="addPhase === 'traits'">
          <Button class="picker-back" variant="link" @click="addPhase = traitsBackPhase">← {{ selectedTraitSet?.name }}</Button>
          <h4 v-if="selectedRelationship">For {{ displayName(selectedRelationship.name) }}</h4>
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
    <!-- The roaming GM's play surface. A GM who is not viewing an entity has no
         sheet to show, and the Play tab they used to reach through the panel now
         lives here — so this is the body the old "No entity loaded" placeholder
         stood in. Same view chain as the entity body above: a question takes the
         panel, the overview is what is otherwise there. -->
    <template v-else-if="gmMode">
      <div v-if="sfxChoiceRequest && sfxChoiceRequest.length" class="sheet-sfx-choice">
        <EffectTargetWizard
          :entity-id="sfxSubjectId"
          :pending-choices="sfxChoiceRequest"
          title="Choose a target"
          embedded
          @resolve="onChoiceResolved"
          @cancel="emit('sfx-choice-cancel')"
          @run-loop="(c) => emit('sfx-choice-loop', c)"
        />
      </div>
      <!-- The GM's rules are pressed *here*, so the table they open lands here too
           rather than over the top of the play surface. -->
      <div v-else-if="rollTableMenu" class="sheet-sfx-choice sheet-roll-table">
        <RollTableMenu
          embedded
          :entity-id="sfxSubjectId"
          :table-id="rollTableMenu.tableId"
          :title="rollTableMenu.name"
          :entity-razmerit="entity?.razmerit ?? 0"
          :mode="rollTableMenu.mode || 'apply'"
          :player-id="playerId"
          :main-entity-id="mainEntityId"
          @close="rollTableMenu = null"
        />
      </div>
      <div v-else class="sheet-scroll">
        <GmPlayOverview
          :current-location-id="placeId"
          :current-location-name="placeName"
          :entities="sceneEntities"
          :location-tree="locationTree"
          :in-session="inSession"
          @next-beat="emit('next-beat')"
          @advance-scene="emit('advance-scene')"
          @start-session="emit('start-session')"
          @end-session="emit('end-session')"
          @go-to-location="(id) => emit('go-to-location', id)"
          @inspect="(id) => emit('inspect-entity', id)"
        >
          <!-- The rules that live on the GM rather than on anyone in the scene:
               the manual ones are a press, the rest are stated so the row is not
               silently missing a rule the GM knows they wrote. -->
          <template v-if="gmRuleCards.length" #rules>
            <div class="gm-sfx-rules">
              <div class="gm-sfx-label">On the GM</div>
              <div class="entity-sfx-cards">
                <SfxCard
                  v-for="c in gmRuleCards"
                  :key="c.id"
                  v-bind="c.model"
                  @activate="activateGmRule(c.id)"
                />
              </div>
            </div>
          </template>
        </GmPlayOverview>
      </div>
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
      <!-- Portrait viewer: the sheet's `background` role image (active body first,
           then entity-level), opened as a modal inside this panel. -->
      <div
        v-if="portraitViewerOpen"
        class="portrait-viewer-overlay"
        @click.self="portraitViewerOpen = false"
      >
        <div class="portrait-viewer">
          <div class="portrait-viewer-head">
            <span>{{ entity.name }}</span>
            <Button variant="ghost" size="sm" title="Close" @click="portraitViewerOpen = false">✕</Button>
          </div>
          <MediaImage :src="portraitViewerSrc" class="portrait-viewer-media" :alt="entity.name" />
          <ImageProvenance
            v-if="portraitViewerInfo"
            class="portrait-viewer-prov"
            :flags="portraitViewerInfo.flags || []"
            :credits="portraitViewerInfo.credits || []"
            :license="portraitViewerInfo.license || ''"
            :credit-text="portraitViewerInfo.creditText || ''"
          />
        </div>
      </div>

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
import { useTraitEditor } from '../composables/useTraitEditor.js'
import { useDragDrop } from '../composables/useDragDrop.js'
import { useTraitPlay } from '../composables/useTraitPlay.js'
import ImageProvenance from './ImageProvenance.vue'
import TraitEditPanel from './sheet/TraitEditPanel.vue'
import SfxCard from './sheet/SfxCard.vue'
import EffectTargetWizard from './gm/EffectTargetWizard.vue'
import TraitDetailPanel from './sheet/TraitDetailPanel.vue'
import TraitRow from './sheet/TraitRow.vue'
import DiePicker from './DiePicker.vue'
import BlueBook from './BlueBook.vue'
import LifePathWizard from './LifePathWizard.vue'
import MediaImage from './MediaImage.vue'
import Button from '@/components/ui/Button.vue'
import TraitInstanceEditor from '@/components/ui/TraitInstanceEditor.vue'
import RollTableMenu from './gm/RollTableMenu.vue'
import GmPlayOverview from './gm/GmPlayOverview.vue'
import { useEntityCrud } from '../composables/useEntityCrud.js'
import { useLocationTree } from '../composables/useLocationTree.js'
import { ancestorsOf, canPickUp, carriedNegatives, challengeRemaining, childrenOf, countDescendants, countSetPicks, descendantsOf, hasContents, isContainer, isOpenContainer, groupRelationRows, relationContinuations, rootAnchor, sortSetTraits, subtreeContains, usesFlatTraitList } from '../utils/traitTree.js'
import { splitRefunds } from '../utils/poolSpends.js'
import { rollTableIdFromAnswer, rollTableIdOf, rollTableMenuEffect } from '../utils/rollTableMenu.js'
import { DEFAULT_SHEET_TAB, hasSheetTab, sheetProfileFor } from '../utils/sheetProfile.js'
import { entityTypeBucket, entityTypeRank } from '../constants/entityTypes.js'

const props = defineProps({
  entityId: { type: String, default: null },  // null = GM free-roam (B95); guards at use sites
  universe: { type: String, default: 'earth' },
  phase: { type: String, default: 'adding' },
  embedded: { type: Boolean, default: false },
  // A pending SFX choice **raised from this sheet** (the app shell routes by origin).
  // It renders here rather than in the roller because this is where it was asked: the
  // trait you pressed stays visible behind it, so the question has its context. A
  // roll-time question goes to the roller; an automatic one to a floating panel.
  sfxChoiceRequest: { type: Array, default: () => [] },
  // Whether the traits tab draws the sets as an accordion (B178) or as a drill-in
  // (the shape B178 replaced). The host owns the layout, so it owns this; the
  // rule is the human's — accordion only for landscape views with a large height,
  // i.e. desktops and tablets. Default `false`, the drill-in, because that is the
  // shape that does not need height to work.
  traitSetAccordion: { type: Boolean, default: false },
  gmMode: { type: Boolean, default: false },
  // The place the GM is standing in, and its name — the **GM's** place, which is
  // not the sheet's own `locationName` ref (that one resolves from the entity
  // being viewed). They are deliberately not called the same thing: an earlier cut
  // of this used `locationId`/`locationName`, and the second silently lost to the
  // local ref of that name, so the play surface drew the slug where the panel
  // reads the name (`loc-krasnoyarsk` for "Krasnoyarsk-45"). `place` is the
  // project's word for the location the fiction is standing in (`placeSfxRules`,
  // the "Places" tree), so it also says *whose* location this is.
  placeId: { type: String, default: '' },
  placeName: { type: String, default: '' },
  inSession: { type: Boolean, default: false },
  externalPoolSources: { type: Array, default: null },
  overrideEntityId: { type: String, default: null },
  viewerEntityId: { type: String, default: null },
  playerOwnedEntityIds: { type: Array, default: () => [] },
  visible: { type: Boolean, default: true },
  playerId: { type: String, default: '' },
  mainEntityId: { type: String, default: '' },
})

const emit = defineEmits(['addToPool', 'removeFromPool', 'splitDie', 'removeByTsId', 'retractNegative', 'sfxToggled', 'stampSfx', 'openSettings', 'sheetViewChange', 'viewEntity', 'sfx-choice-answer', 'sfx-choice-cancel', 'sfx-choice-loop', 'next-beat', 'advance-scene', 'start-session', 'end-session', 'go-to-location', 'inspect-entity'])

function displayName(name) {
  return name
    .split('_')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

const { loading, error, graphql, triggerSfx, endSfx, spendResourceDie, recoverResourceDie, spendChallengeDie, recoverChallengeDie } = useApi()

// Playing a trait lives in `composables/useTraitPlay.js`, so a sheet row and a map
// chip play by one set of rules. This is the sheet's half of that contract: its pool
// bookkeeping. The viewer passes no-ops for the parts it does not have (there is no
// pool tree on the map), and the shared gates/payload shapes come from the composable.
const traitPlay = useTraitPlay({
  phase: () => props.phase,
  cascade: (t) => cascadeGroup(t),
  addToPool: (payload) => emit('addToPool', payload),
  notePick,
  displayName,
  armedSfxIdsFor: armedSfxIdsForTrait,
  spendResourceDie,
  spendChallengeDie,
  rememberSpend: (tsId, entry) => {
    if (!refundableSpends.value[tsId]) refundableSpends.value[tsId] = []
    refundableSpends.value[tsId].push(entry)
  },
  refresh: (reason) => fetchEntity(reason),
})
const entityCache = useEntityCache()
const { fetchFor: fetchScheduledEvents, formatTimers } = useScheduledEvents()
const entity = ref(null)
// **Which entity this sheet is showing** — the perspective, which is what the
// props say, and the only thing that can say "nobody". `entity` below is a *cache*
// of the fetch for that id, so it is not the authority on whether there is a sheet
// to draw: a perspective can be dropped without another being taken up (a GM
// returning to free-roam), and until this gate existed the stale cache kept the
// entity branch rendering and the roaming GM's play surface unreachable (the
// author, 2026-09-29).
const shownEntityId = computed(() => props.overrideEntityId || props.entityId)
// A primitive gate for the body's `v-if` chain. Binding the branch to the
// entity *object* kept a stable identity anyway (Vue keys `v-if` branches by
// index), but read as if a refresh would remount; `hasEntity` says what is
// meant, and pairs with the `!hasEntity &&` guards above so a refresh patches
// in place instead of rebuilding (B125).
//
// Both conjuncts carry weight. `shownEntityId` is the decision; `entity` is the
// payload, and without it the branch would render an entity-shaped hole for the
// moment a perspective is taken up but not yet fetched. Reading the props here
// also means the branch flips with the perspective rather than with a watcher or
// a response — the failure mode this replaces.
const hasEntity = computed(() => !!shownEntityId.value && !!entity.value)
const activeProjection = computed(() => {
  const e = entity.value
  if (!e || !e.projections) return null
  return e.projections.find((p) => p.id === e.currentProjection) || null
})
const sheetPortrait = computed(() => activeProjection.value?.sheetImage || entity.value?.sheetPortrait || '')

// Portrait viewer (modal). Shows the character's `background` role image —
// resolved through the active body first, then entity-level — falling back to
// the portrait itself when no background image exists.
const portraitViewerOpen = ref(false)
const portraitViewerSrc = computed(() => entity.value?.backgroundRoleImage || sheetPortrait.value)
// What the viewer should *disclose* about that picture — its AI labels and its
// credits/citation. Fetched when the viewer opens rather than with the sheet:
// it is metadata for a modal, not something the sheet needs to render.
const portraitViewerInfo = ref(null)

watch(portraitViewerOpen, async (open) => {
  if (!open || !entity.value) return
  const id = entity.value.id
  portraitViewerInfo.value = null
  try {
    const data = await graphql(
      `query($id: ID!) {
        entity(id: $id) {
          imageInfo(role: "background") {
            url flags license creditText
            credits { role name url }
          }
        }
      }`,
      { id }
    )
    // The viewer may have been closed or moved on while that was in flight.
    if (portraitViewerOpen.value && entity.value?.id === id) {
      portraitViewerInfo.value = data?.entity?.imageInfo || null
    }
  } catch {
    portraitViewerInfo.value = null
  }
})
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
// Rules this entity — or the body it is wearing — simply **has**, from a granted
// reach declaration ([[Dynamic SFX Reach]]). `sfxIds` is what is *attached*, and a
// granted rule attaches nothing, so the attached lists alone can never show one:
// the rule is available and invisible. Read-time like the trait rows'
// `grantedSfxIds`, and separate from `sfxIds` for the same reason — the entity
// editor writes that list back wholesale, so folding would materialise the grant
// on the first save.
const entityGrantedSfxIds = computed(() => entity.value?.grantedSfxIds || [])
const projectionGrantedSfxIds = computed(() => activeProjection.value?.grantedSfxIds || [])
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

/** The set's rules that are *granted* to it rather than attached — see above. */
function traitsetGrantedSfxIds(ts) {
  const tss = traitSetSettingsByTraitsetId.value[ts.traitsetId]
  return (tss && tss.grantedSfxIds) || []
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

// Which rule booked the timers running on this trait. A countdown is only half
// the story — "1 beat" with no origin is a mystery; the row carries the rule it
// came from (`sourceSfxName`), and several rules can stack timers on one trait.
function traitTimerOrigin(t) {
  const evs = timersByTraitId.value[t.id]
  if (!evs || !evs.length) return ''
  return [...new Set(evs.map((ev) => ev.sourceSfxName).filter(Boolean))].join(', ')
}

// The countdown line is re-fetched at every moment a timer can tick (a roll, an
// SFX ending). The display depends only on each row's owner, countdown and
// combine mode, so assign only when that projection actually differs — an
// unchanged fetch must not re-render the sheet.
function timerDisplayKey(events) {
  return JSON.stringify((events || []).map((ev) => [
    ev.id, ev.targetId, ev.combine,
    (ev.timers || []).map((t) => [t.event, t.remaining]),
  ]))
}

function assignIfChanged(ref, next) {
  if (timerDisplayKey(ref.value) === timerDisplayKey(next)) return
  ref.value = next
}

async function fetchTimers() {
  const eid = props.overrideEntityId || props.entityId
  if (!eid) return
  const e = epoch()
  const tsIds = (allTraitSettings.value || []).map((t) => t.id)
  const [ent, ts] = await Promise.all([
    fetchScheduledEvents('entity', eid),
    tsIds.length ? fetchScheduledEvents('trait_setting', null, tsIds) : Promise.resolve([]),
  ])
  if (stale(e)) return
  assignIfChanged(entityTimers, ent || [])
  assignIfChanged(traitSettingTimers, ts || [])
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
    .map(({ name, traits, traitsetId, order, limit }) => ({ name, traits: sortSetTraits(traits), traitsetId, limit }))
}

function recomputeTraitSets(reason = 'unspecified') {
  const src = showAllTraits.value ? allTraitSettings.value : effectiveSettings.value
  const settings = src || []
  // Which tab a trait belongs on is the trait *set's* decision now, not the
  // rating's: a container trait carries no rating either, so `ratingType` could
  // never tell it apart from a genuinely descriptive trait.
  const onProfile = (t) => t.traitsetTab === 'PROFILE'
  profileTraits.value = settings.filter(onProfile)
  traitSets.value = groupTraitSettings(settings.filter(t => !onProfile(t)))
  // Every rebuild is a fresh array of set objects, so the list re-renders even
  // when the membership is identical — worth seeing while chasing the reload.
  perfMark('trait-sets-rebuilt', { reason, sets: traitSets.value.length })
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

// ── Which sheet this is (B108 / B134) ──────────────────────────────
// One shell, three faces: an occupant, a location, a faction. The declaration
// lives in `utils/sheetProfile.js` (tabs + header extras only) because the trait
// machinery below is already type-agnostic and must stay that way.
const sheetProfile = computed(() => sheetProfileFor(entity.value?.type))
const isFactionSheet = computed(() => sheetProfile.value.kind === 'faction')
function hasTab(tab) { return hasSheetTab(sheetProfile.value, tab) }

// ── Faction roster (B108) ───────────────────────────────────────
// A faction's members live on `membership` edges (plus the promoted `relation`
// ties), which is exactly what `factionMembers` resolves. Fetched lazily on the
// tab rather than with the entity: a faction sheet that is never opened on the
// roster should not pay for it.
const roster = ref([])
const rosterLoading = ref(false)

function memberTypeBadge(type) {
  const t = String(type || '').toUpperCase()
  if (t === 'CHARACTER') return 'PC'
  return t || '—'
}

async function fetchRoster() {
  const id = props.overrideEntityId || props.entityId
  if (!id || !isFactionSheet.value) { roster.value = []; return }
  rosterLoading.value = true
  const data = await graphql(
    `query($id: ID!) { factionMembers(factionId: $id) { id name type role rank } }`,
    { id },
  )
  roster.value = data?.factionMembers || []
  rosterLoading.value = false
}

watch(
  [() => activeSheetView.value, () => props.entityId, () => props.overrideEntityId, isFactionSheet],
  () => { if (activeSheetView.value === 'roster') fetchRoster() },
  { immediate: true },
)

// The trait-setting fields a relationship query must ask for: exactly what
// `TraitRow` and the detail read. Shared by the outgoing relation query and the
// incoming-ties one so the two cannot drift — a field the UI reads but a query
// omits is invisible, the family of bug this file has hit more than once.
const RELATION_TRAIT_FIELDS = `
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
  traitsetTab
  knownTo
  possibleSfxIds
  tags
  registryTags
  relationshipContactId
  relationshipContactName
  relationshipContactType
  relationshipType
  possibleSubtraitIds
  # The trait's picture (B200), aliased to the names the registry query already
  # uses (useTraitsConfig) so one vocabulary serves both reads. "sheet" is the
  # row/detail picture, "background" the detail's backdrop, and the bare
  # imageTransparent is that ladder's default role -- "sheet".
  sheetImage: image(role: "sheet")
  backgroundImage: image(role: "background")
  imageTransparent
`

// ── Incoming ties (B134) ────────────────────────────────────────
// What *others* hold about this entity — the mirror of the relation tab, which
// is our outgoing edge. There is no dedicated read for it yet: every repository
// method filters `_from` (see the ask to [[backend-platform]] in the session
// doc), so it is composed from two queries that do exist:
//
//   1. `relatedEntities(id)` — undirected, so it asks no direction question and
//      needs no knowledge of which peers might point at us;
//   2. one `relationship(from: peer, to: us)` per peer, which returns non-null
//      **exactly** when that peer holds a `relation` tie about us. So the
//      direction filter is the API's answer, not a guess — a `super` parent or
//      child comes back null and drops out on its own.
//
// The fan-out is bounded and small — measured across all 410 locations: median 2
// peers, p95 10, max 20 — so the N+1 is a single concurrent burst rather than a
// problem. When a real incoming read lands, **this function is the only thing
// that changes**; the view above it does not care how the ties were found.
//
// **Known blind spot, measured rather than assumed.** `relatedEntities` joins the
// peer it finds to the `entities` collection by key, so an edge whose holder is a
// **projection** (`projections/<id>:<universe>`, a body-level tie) resolves to no
// entity and is dropped before this code ever sees it. Live: of **93** incoming
// location ties, **1** is projection-held, so the composition covers **92**; no
// location has two edges from the same holder, so nothing else is collapsed. A
// dedicated read — which would filter `_to` and resolve `_from` without the join
// — is the only way to close that, because nothing client-side can name an edge
// whose holder never came back. See the ask to [[backend-platform]].
const incomingTies = ref([])
const incomingTiesLoading = ref(false)

async function fetchIncomingTies() {
  const id = props.overrideEntityId || props.entityId
  if (!id || !hasTab('ties')) { incomingTies.value = []; return }
  incomingTiesLoading.value = true
  const peerData = await graphql(
    `query($id: ID!) { relatedEntities(entityId: $id) { id name type } }`,
    { id },
  )
  const peers = peerData?.relatedEntities || []
  const found = await Promise.all(peers.map(async (p) => {
    const data = await graphql(
      `query($from: ID!, $to: ID!) {
        relationship(fromEntityId: $from, toEntityId: $to) {
          id
          description
          relationTraits { ${RELATION_TRAIT_FIELDS} }
        }
      }`,
      { from: p.id, to: id },
    )
    const edge = data?.relationship
    if (!edge) return null
    return {
      edgeId: edge.id,
      description: edge.description || '',
      holderId: p.id,
      holderName: p.name,
      holderType: p.type,
      traits: edge.relationTraits || [],
    }
  }))
  incomingTies.value = found.filter(Boolean)
  incomingTiesLoading.value = false
}

// Fetched on the entity rather than on the tab, because whether the tab should
// exist at all is the fetch's answer — and a 🔗 that opens onto "nobody holds a
// tie here" for 353 of 410 locations is chrome, not information. The relation
// tab already follows this convention.
const showTiesTab = computed(() => hasTab('ties') && incomingTies.value.length > 0)

watch(
  [() => props.entityId, () => props.overrideEntityId, sheetProfile],
  () => { if (hasTab('ties')) fetchIncomingTies(); else incomingTies.value = [] },
  { immediate: true },
)

// ── Relation tab (foreign sheets) ───────────────────────────────
// Traits hanging off *our* outgoing edge to the sheet we're looking at — what we
// hold about them (`_from == viewerEntityId`, `_to == overrideEntityId`). The tab
// only exists when such an edge carries traits; a bare edge isn't worth a tab.
const relationTraits = computed(() => relationship.value?.relationTraits || [])
const showRelationTab = computed(() => !!isForeignSheet.value && relationTraits.value.length > 0)

// `activeSheetView` is persisted, so a view can outlive the entity that
// justified it: 'relation' when the edge goes away, 'lifepath' when the sheet
// switches to a location, 'roster' when it switches to a character, 'ties' when
// the last tie is removed. One rule rather than three branches — the tabs the
// profile declares, minus the two that are conditional on there being something
// to show, plus 'relation' when there is. Immediate, because the profile is the
// occupant's until `entity` arrives, so the correction has to re-run when it does.
const availableViews = computed(() => {
  const views = new Set(sheetProfile.value.tabs)
  if (!showTiesTab.value) views.delete('ties')
  if (showRelationTab.value) views.add('relation')
  return views
})
watch(availableViews, (views) => {
  if (!views.has(activeSheetView.value)) activeSheetView.value = DEFAULT_SHEET_TAB
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
    await fetchEntity('projection-name-save')
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

// Traits with an EMPTY rating type, shown flat on the profile tab.
const profileTraits = ref([])

// ── Containers ────────────────────────────────────────────────────
// A container collapses until it is opened. The open set is persisted like the
// sheet's other state because the sheet refetches constantly (SSE, mutations);
// a container that snapped shut on every refetch would be unusable.
const expandedContainers = usePersistedRef('sheet.expandedContainers', [])
function isExpanded(t) {
  return expandedContainers.value.includes(t.id)
}
function toggleExpand(t) {
  expandedContainers.value = isExpanded(t)
    ? expandedContainers.value.filter((id) => id !== t.id)
    : [...expandedContainers.value, t.id]
}
function containerCount(t) {
  return countDescendants(t)
}

// ── Drag a trait into a container ────────────────────────────────
// Direct manipulation, and the reason no authoring is needed first: nothing on
// the write path checks a container against the registry's nominations, so any
// trait can go into any container.
//
// Which ROOT rows carry a grip: only while some open container can receive them
// (see isOpenContainer), so grips never clutter an ordinary sheet, and a
// container is never draggable into itself or into its own descendants.
// Which rows have somewhere to go: some OPEN container that is neither the row
// itself nor anywhere inside it. Computed for **every** row, not just the roots,
// because a row inside a container is draggable at any depth now and needs the
// same answer — for a nested row it is normally its own parent, and the
// subtree exclusion is what keeps a container from being offered a drop into its
// own descendant at any level.
const draggableRowIds = computed(() => {
  // The rows on screen, whichever way the list is scoped — and for the accordion
  // that means the *open* sets, since a collapsed set has no container to drop
  // into and no row to pick up.
  const roots = visibleRows.value || []
  const open = []
  const collect = (list) => {
    for (const t of list || []) {
      if (isOpenContainer(t, isExpanded(t))) open.push(t)
      collect(childrenOf(t))
    }
  }
  collect(roots)
  const ids = new Set()
  const consider = (t) => {
    if (open.some((c) => c.id !== t.id && !subtreeContains(t, c.id))) ids.add(t.id)
    for (const child of childrenOf(t)) consider(child)
  }
  roots.forEach(consider)
  return ids
})

// Depth decides what counts as "part of its parent": see canPickUp. A row inside
// a container may be picked up at any depth; a sub-trait of a non-container never
// moves, however deep it is.
function canDrag(t, depth = 0, insideContainer = false) {
  return canPickUp({ depth, insideContainer, hasDestination: draggableRowIds.value.has(t.id) })
}

function dragPayload(t) {
  return { id: t.id, nested: t.fromType === 'traitsetting', parent: t.parentTraitsettingId || null }
}

const { dragging, source, over, touchStart, dragStart, dragOver, dragLeave, drop, dragEnd } = useDragDrop({
  // A container row takes the trait. Any OTHER row means "out of its container"
  // — back to the top level of the set. Using every non-container row as that
  // zone is deliberate: on touch the target has to be forgiving, and the row you
  // drag past on the way out of an indented list is exactly the one above the
  // container.
  resolveTarget: (el) => {
    const row = el && el.closest ? el.closest('[data-ts-id]') : null
    if (!row) return null
    return row.dataset.dropContainer ? { id: row.dataset.dropContainer } : { id: null }
  },
  ghostSource: (el) => (el && el.closest ? el.closest('[data-ts-id]') : el),
  onCommit: ({ from, to }) => {
    suppressClicks()
    if (to.id) {
      if (to.id !== from.parent) moveTraitInto(from.id, to.id)
    } else if (from.nested) {
      moveTraitOut(from.id)
    }
  },
})

// Dropping a trait into a container is **direct manipulation**: any trait the
// sheet is showing may go in, not only the ones the container's definition
// nominates. That is deliberate, not an oversight — the write path refuses only
// cycles and cross-entity parents, and says the same thing in
// `mutations_traitsettings` under `from_type: 'traitsetting'`. The editor's
// sub-trait list offers the nomination as a *shortcut* to the traits a container
// was authored for (see `availableSubtraits` in useTraitEditor); it is guidance,
// not a gate. The two paths disagree about the list and agree about the intent,
// which is the decision B142 asked to have recorded rather than left as an
// accident. Changing that — gating the drop or widening the editor — is a design
// call, not a cleanup.
async function moveTraitInto(traitSettingId, containerId) {
  if (!traitSettingId || !containerId || traitSettingId === containerId) return
  perfMark('trait-move-start', { traitSettingId, containerId })
  const result = await graphql(`mutation($id: ID!, $input: TraitSettingUpdateInput!) {
    updateTraitSetting(id: $id, input: $input) { id fromType parentTraitsettingId }
  }`, {
    id: traitSettingId,
    input: { fromType: 'traitsetting', parentTraitsettingId: containerId },
  })
  // graphql() returns null on error rather than throwing; the message is already
  // in `error`, and moving on would refetch a sheet that did not change.
  if (!result) return
  // Show where it went: open the container so the trait that just landed in it
  // is visible instead of appearing to have vanished.
  if (!expandedContainers.value.includes(containerId)) {
    expandedContainers.value = [...expandedContainers.value, containerId]
  }
  await fetchEntity('trait-move-in')
}

async function moveTraitOut(traitSettingId) {
  // Come out as whatever anchors the chain: a child of a morph container returns
  // to morph on the same body rather than silently becoming ego. Mirrors how
  // nesting inherits its anchor.
  const anchor = rootAnchor(visibleRows.value || [], traitSettingId)
  const input = anchor && anchor.fromType === 'projection' && anchor.projectionId
    ? { fromType: 'projection', projectionId: anchor.projectionId }
    : { fromType: 'entity' }
  perfMark('trait-move-out-start', { traitSettingId, to: input.fromType })
  const result = await graphql(`mutation($id: ID!, $input: TraitSettingUpdateInput!) {
    updateTraitSetting(id: $id, input: $input) { id fromType parentTraitsettingId }
  }`, { id: traitSettingId, input })
  if (!result) return
  await fetchEntity('trait-move-out')
}

function onTraitDragStart(e, t) { dragStart(e, dragPayload(t)) }
function onGripTouchStart(e, t) { touchStart(e, dragPayload(t), { instant: true }) }
function onTraitDragOver(e) { dragOver(e) }
function onTraitDragLeave() { dragLeave() }
function onTraitDrop(e) { drop(e) }
function onTraitDragEnd() { dragEnd() }
function isDragOver(t) { return over.value?.id === t.id }
function isDragging(t) { return dragging.value && source.value?.id === t.id }

// A drop lands on the row under the pointer and the browser then fires a click
// there, which would toggle the container we just dropped into. Swallow it.
let suppressClickUntil = 0
function clickSuppressed() { return Date.now() < suppressClickUntil }
function suppressClicks() { suppressClickUntil = Date.now() + 200 }

// ── The set accordion ───────────────────────────────────────────────────
// Every set is a section with its traits under it, and they all start **closed**:
// the sets are a short list you scan, and opening one is a deliberate act.
//
// Which are open is **persisted**, like the container state — a reload in the
// middle of arranging a sheet should put you back where you were rather than
// collapsing everything under you. An array, not a `Set`: this writes through
// `JSON.stringify`, and a Set serialises to `{}`.
const openSets = usePersistedRef('sheet.openTraitSets', [])

const isSetOpen = (name) => openSets.value.includes(name)

function toggleSet(name) {
  if (isSetOpen(name)) {
    collapseSet(name)
    return
  }
  openSets.value = [...openSets.value, name]
  // Entering a set collapses *its* containers — their contents are something you
  // look into deliberately, not state carried over from last time. This is the
  // rule the drill-in applied on set entry; per set now, because several sets can
  // be open at once and one set's entry must not close another's.
  collapseContainersIn(name)
}

/** Close a set without opening it if it was already shut. */
function collapseSet(name) {
  if (!isSetOpen(name)) return
  openSets.value = openSets.value.filter(n => n !== name)
}

/** Open a set without toggling it shut, for landing on a trait that just appeared. */
function expandSet(name) {
  if (!name || isSetOpen(name)) return
  openSets.value = [...openSets.value, name]
}

function collapseContainersIn(name) {
  const set = traitSets.value.find(ts => ts.name === name)
  if (!set) return
  const inside = new Set()
  for (const root of set.traits || []) {
    inside.add(root.id)
    for (const child of descendantsOf(root)) inside.add(child.id)
  }
  expandedContainers.value = expandedContainers.value.filter(id => !inside.has(id))
}

// ── The set drill-in ────────────────────────────────────────────────────
// The shape the sets take where there is **no height to spare** — every view but
// a landscape desktop or tablet (`props.traitSetAccordion`). The accordion shows
// every set at once, which needs a tall sheet; a phone has a short one, so it
// gets the list-then-one-set shape instead: the set list as navigation, then that
// set's traits on their own.
//
// One name, not a stack: this is "which set am I looking at", and the back
// control and the set list are the only two places you can be. Persisted like the
// accordion's open sets, because it is the reader's position on the sheet and
// losing it on reload is the same surprise the human reported there.
const drilledSetName = usePersistedRef('sheet.traitSetDrill', null)

const drilledSet = computed(() =>
  drilledSetName.value ? traitSets.value.find(ts => ts.name === drilledSetName.value) || null : null)

function openSet(name) {
  if (!name) return
  drilledSetName.value = name
  // Containers start closed every time a set is entered: their contents are
  // something you look into deliberately, not state carried over from last time.
  collapseContainersIn(name)
}

function closeSet() {
  drilledSetName.value = null
}

// Where you were in the set order, for the two buttons under a set's traits. The
// order is the sheet's own (`traitSets` is sorted by the set's `order`).
const drilledSetIndex = computed(() =>
  drilledSet.value ? traitSets.value.indexOf(drilledSet.value) : -1)
const prevSet = computed(() => (drilledSetIndex.value > 0 ? traitSets.value[drilledSetIndex.value - 1] : null))
const nextSet = computed(() => {
  const i = drilledSetIndex.value
  return i >= 0 && i < traitSets.value.length - 1 ? traitSets.value[i + 1] : null
})
const goToPrevSet = () => prevSet.value && openSet(prevSet.value.name)
const goToNextSet = () => nextSet.value && openSet(nextSet.value.name)

/**
 * Put the reader on a set's traits, in whichever shape the tab is drawing — the
 * accordion opens the section, the drill-in enters it. One call site for each
 * intent, so the two shapes cannot drift into different behaviour.
 */
function landOnSet(name) {
  if (!name) return
  if (props.traitSetAccordion) expandSet(name)
  else openSet(name)
}

/**
 * Hand the reader the next set when the one they just picked from fills its
 * limit — in **both** shapes: the drill-in enters the next set's list, the
 * accordion closes the finished section and opens the next.
 *
 * The check belongs *here*, on the pool update, and not where the pick was made.
 * `isInPool` reads the pool the **host** owns, so at click time the new die is
 * not in it yet and any count taken there is a guess — which is the race that
 * made this look unsafe to build. `setPoolSources` runs when the host pushes the
 * changed sources back, which is the first moment the answer is true and the same
 * trigger the sheet used before the accordion.
 *
 * The finished set is closed so the next one takes its place rather than being
 * pushed below the reader's eye — "the next set appears" has to mean it is where
 * they are looking. Several sets can be open at once, so closing this one costs
 * nothing the reader did not just finish with.
 */
function advanceToNextSetIfFull() {
  const name = justPickedSet.value
  justPickedSet.value = null
  if (!name) return
  // A flat sheet has no set layer: there is no next set to be handed.
  if (flatTraitList.value) return
  const i = traitSets.value.findIndex(ts => ts.name === name)
  if (i === -1) return
  const set = traitSets.value[i]
  if (!setIsFull(set)) return
  const next = traitSets.value[i + 1]
  if (!next) {
    // Nothing left to fill. The drill-in comes back out to the list rather than
    // sitting on a set that cannot take another pick; the accordion already has
    // every set on screen, so there is nowhere to go and nothing to do.
    if (!props.traitSetAccordion) closeSet()
    return
  }
  if (props.traitSetAccordion) collapseSet(name)
  landOnSet(next.name)
}

// The 🎲 pill is "the traits, from the top": with a drill-in the top is the set
// list, so it also comes back out of whichever set was open.
function goToTraitSets() {
  activeSheetView.value = 'traits'
  cancelEdit()
  drilledSetName.value = null
}

// The accordion's rows: each set's traits, grouped so a relationship's rows sit
// together, with the ids whose `→ contact` the row above already states.
const accordionSets = computed(() => traitSets.value.map(ts => {
  const traits = groupRelationRows(ts.traits)
  return { ts, traits, continuations: relationContinuations(traits) }
}))

// B60 — a sheet with few traits skips the set-list layer: the sets are a
// navigation device, and with a handful of traits there is nothing to navigate.
// The list itself is the same either way; only the layer above it changes, so a
// container, a sub-trait and a die all read exactly as they do when drilled in.
// Adding to a sheet is the owner's (or a GM's) act: a player looking at someone
// else's sheet sees the traits and no way in. One expression for both the set
// header's [+] and the button below the list, so the two cannot drift apart.
const canAddTraits = computed(() => !props.overrideEntityId || props.gmMode)

const flatTraits = computed(() => traitSets.value.flatMap(ts => ts.traits))
const flatTraitList = computed(() => usesFlatTraitList(traitSets.value))

// ── Filling a set hands the reader the next one ──────────────────────────
// Which set the reader has just put a pick into, remembered so `setPoolSources`
// can answer "did that fill it?" — see `advanceToNextSetIfFull` for why the
// answer cannot be computed where the pick was made.
const justPickedSet = ref(null)

/**
 * The set a pick belongs to, found **at any depth**.
 *
 * A sub-trait rides its parent's set, so playing one fills that set rather than
 * nothing. `setOfTrait` scans a set's *roots* only, which is right for the
 * row-level questions it answers and wrong for this one.
 */
function setNameOfPick(tsId) {
  if (!tsId) return null
  return traitSets.value.find(ts => (ts.traits || []).some(root => subtreeContains(root, tsId)))?.name || null
}

/** Remember the set a pick just went into; consumed by the next pool update. */
function notePick(tsId) {
  justPickedSet.value = setNameOfPick(tsId)
}

/**
 * Whether a set's picks are all in the pool — the same test the limit dots fill
 * on, so the readout and the behaviour cannot disagree.
 */
function setIsFull(set) {
  return !!set?.limit && countSetPicks(set.traits, isInPool) >= set.limit
}

// A stale drill must not survive the set it named. Two ways it goes stale: the
// sheet drops under the flat limit (there is no set layer then), or the sets are
// rebuilt without it (a universe change replaces every set). Placed here rather
// than with the drill state because it reads `flatTraitList`, and `watch` runs
// its source getters during setup — above this line that is a TDZ error.
watch([traitSets, flatTraitList], () => {
  if (drilledSetName.value && (!drilledSet.value || flatTraitList.value)) drilledSetName.value = null
})

// The list a single-list branch renders: the profile tab, the relation tab, the
// flat sheet (B60), or the set the reader has drilled into. The accordion renders
// each set itself, so on the traits tab under the accordion there is no
// single list — `visibleRows` is what knows about the open sets.
const currentTraits = computed(() => {
  if (activeSheetView.value === 'relation') return relationTraits.value
  if (activeSheetView.value === 'profile') return profileTraits.value
  if (flatTraitList.value) return groupRelationRows(flatTraits.value)
  if (props.traitSetAccordion) return []
  return groupRelationRows(drilledSet.value?.traits || [])
})

// Rows whose `→ contact` the row above already states. Computed over whatever
// list is rendering, so the relations set, the flat list and the relation tab all
// group the same way; the rule itself lives in the model (utils/traitTree.js) so
// it can be checked without a browser.
const traitContinuations = computed(() => relationContinuations(currentTraits.value))

// Every root row the traits area is showing, however it is scoped: the flat list
// (B60), the accordion's open sets, the drilled set, the profile tab or the
// relation tab. Drag destinations and the move-out anchor ask this rather than
// `currentTraits`, which is the single-list views only.
const visibleRows = computed(() => {
  if (activeSheetView.value === 'traits' && !flatTraitList.value && props.traitSetAccordion) {
    return accordionSets.value.filter(e => isSetOpen(e.ts.name)).flatMap(e => e.traits)
  }
  return currentTraits.value || []
})

// Whether a row's set has used up its picks. The flat list mixes sets, so the
// answer has to be found per row; drilled into one set, the lookup returns that
// same set. Counts *picks*, not settings: a sub-trait rides its parent, while a
// container contributes its children instead of itself.
function limitReachedFor(t) {
  const set = setOfTrait(t)
  if (!set || !set.limit) return false
  return countSetPicks(set.traits, isInPool) >= set.limit
}

/** The set a trait instance belongs to, as the sheet groups the settings. */
function setOfTrait(t) {
  return traitSets.value.find(ts => ts.traits.some(x => x.id === t.id)) || null
}

/**
 * Land the reader back on the set list after adding a rating from the detail
 * view (B185). The sets are an accordion (B178), not a drill-in, so "the
 * traitset's trait list" is the set they came from — *opened*, since landing on
 * a collapsed header would read as "the trait vanished". Nothing is closed: the
 * sets a reader opened are theirs to keep, and several being open at once is the
 * point of the accordion.
 *
 * B185 also asks to advance to the *next* set once this one's limit is reached.
 * That clause belongs to the drill-in: the accordion has all the sets on screen
 * at once with the limit dots filling as you pick, so there is no next list to
 * go to, and the "full" answer only exists after the pool has round-tripped —
 * which would make navigation off it racy. Recorded on the ticket, not built.
 */
function backToSetList(t) {
  // Leaving the detail *is* the return; the rest is where it lands.
  closeTraitDetail()
  // Only the traits tab has a set list to come back to. The profile and relation
  // tabs render their rows directly, so returning is just the line above — and
  // expanding a set there would silently open a section of a *different* tab
  // that the reader never asked for.
  if (activeSheetView.value !== 'traits' || flatTraitList.value) return
  const set = setOfTrait(t)
  if (!set) return
  // When that pick filled the set, the advance owns where the reader lands — it
  // moves them on to the next set, or out to the list. Re-opening the set they
  // have just finished with would undo it. Both orders need this: if the pool has
  // already come back, this sees a full set and stands aside; if it has not, it
  // opens the set and the advance closes it again a moment later.
  if (setIsFull(set)) return
  // Belt and braces: a row can only be clicked from inside its own set — open in
  // the accordion, entered in the drill-in — so this is normally already
  // satisfied. It states the requirement rather than relying on that, so a future
  // entry point into the detail cannot land on a collapsed header or the set list
  // and read as "the trait vanished".
  landOnSet(set.name)
}

// SFX usage tracking — reset per dice pool cycle
const sfxActivations = ref({})
const seededInFlight = ref(new Set())  // what the server last reported as in flight
const sfxCatalog = ref({})  // sfxId → { name, description }
const availableSfxIds = ref(null)  // null = not loaded; else the conditions-filtered id list
// Why a listed-but-unavailable rule is unavailable: id -> [phrase per unmet
// condition]. `availableSfxIds` can only say yes/no, which is how a card ends up
// greyed with no reason ([[B193]]); the server answers the *which*.
const sfxUnmetReasons = ref({})
// The rules the place you're standing in lends you: [{ locationId, locationName,
// sfxIds }]. Nothing is attached to the entity — this is where the place's own
// rules get a button to be pressed, which attached-only strips never gave them.
const placeRuleGroups = ref([])
// The rules that live on the **GM** (`sfxOwners(ownerType: GM)`, the same
// attachment read the prep manager edits). They belong to no entity, so nothing
// on any sheet ever drew them, and a manual rule with no card is a rule the GM
// cannot press (the author, 2026-09-29). Only asked for in gmMode.
const gmSfxIds = ref([])
const rollTableMenu = ref(null)  // { sfxId, tableId, name } | null
const SFX_PHASES = {
  'sfx-hinder': ['adding'],
  'sfx-spray-n-pray': ['adding'],
}
const poolSources = ref([])

// Trait-setting ids routed to the opponent's pool (negative traits offered
// during a contest) — highlighted in the sheet and counted toward the set limit.
const offeredTraits = ref(new Set())

// Dice spent out of a trait into the pool, kept so they can be refunded if the
// pool drops them before rolling. { tsId: [{ die, kind }, ...] } — `kind` picks
// the recover path ('resource' → spent ledger, 'challenge' → outright refund).
const refundableSpends = ref({})


const RATING_TYPES = [
  { id: 'STATIC', label: 'Static' },
  { id: 'RESOURCE', label: 'Resource' },
  { id: 'CHALLENGE', label: 'Challenge' },
  { id: 'EMPTY', label: 'Empty' },
]

let longPressTimer = null

// ── Add trait picker ────────────────────────────
const showAddTrait = ref(false)
const addPhase = ref('sets')
const addMode = ref('trait')  // 'trait' | 'relationship'
const availableTraitSets = ref([])
const availableTraits = ref([])
const selectedTraitSet = ref(null)

// ── The relationship step (relations traitset only) ──────────────
// A trait in the `relations` set is not an entity trait: it is anchored to a
// relationship edge, which is why adding one needs to know *whose* relationship.
// Hence one extra step for this set, and only for this set.
//
// The set is identified by name, matching `useFactionRoles`'s `RELATIONS_SET` —
// the registry is keyed by name for this (it holds duplicate trait names resolved
// by set), and a second signal for the same thing would be a second thing to keep
// in step.
const RELATIONS_SET = 'relations'
const selectedRelationship = ref(null)
const relationships = ref([])
const relationshipsLoading = ref(false)
const relationshipFilter = ref('')

const isRelationsSet = (ts) => ts?.name === RELATIONS_SET

const filteredRelationships = computed(() => {
  const q = relationshipFilter.value.trim().toLowerCase()
  if (!q) return relationships.value
  return relationships.value.filter(c => String(c.name || '').toLowerCase().includes(q))
})

const filteredTraits = computed(() => {
  if (!selectedTraitSet.value) return []
  const inSet = availableTraits.value.filter(t => t.traitsetId === selectedTraitSet.value.id)

  // A relationship trait's identity is `{edge}:{trait}`, so the same definition
  // may sit on two different relationships — "already assigned" is per *edge*
  // here, not per entity. The entity-wide set below would hide `loyalty` from
  // every contact because it is on one of them, which defeats the point of a
  // relationships set (and it did: it hid four of the set's twenty-four traits).
  if (addMode.value === 'relationship') {
    const onThisEdge = new Set((relationTraits.value || []).map(t => t.traitId || t.id))
    return inSet.filter(t => !onThisEdge.has(t.id))
  }
  if (isRelationsSet(selectedTraitSet.value) && selectedRelationship.value) {
    const contactId = selectedRelationship.value.id
    const onThisEdge = new Set((allTraitSettings.value || [])
      .filter(s => s.fromType === 'relationship'
        && s.relationshipType === 'relation'
        && s.relationshipContactId === contactId)
      .map(s => s.traitId))
    return inSet.filter(t => !onThisEdge.has(t.id))
  }

  // A set with allow_duplicates can hold several instances of the same trait
  // definition (e.g. two weapons, distinguished by statement), so don't drop
  // already-assigned traits there. Otherwise a trait may be assigned once.
  if (selectedTraitSet.value.allowDuplicates) return inSet
  const assigned = new Set([
    ...traitSets.value.flatMap(ts => ts.traits.map(t => t.traitId || t.id)),
    ...profileTraits.value.map(t => t.traitId || t.id),
  ])
  return inSet.filter(t => !assigned.has(t.id))
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

/**
 * Open the add-trait picker.
 *
 * With no argument it starts at the set list — that is how a trait from a set the
 * sheet has none of yet is reached, since only sets the entity holds appear in the
 * accordion. A set header's `[+]` passes its own set and lands on that set's list
 * (or the relationship step first, for the relations set).
 */
async function openAddTrait(presetSet = null) {
  addMode.value = 'trait'
  addPhase.value = 'sets'
  selectedTraitSet.value = null
  selectedRelationship.value = null
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
  showAddTrait.value = true
  if (presetSet) {
    const target = availableTraitSets.value.find(ts => ts.id === presetSet.traitsetId)
    if (target) selectSet(target)
  }
}

async function openAddRelationshipTrait() {
  addMode.value = 'relationship'
  addPhase.value = 'sets'
  selectedTraitSet.value = null
  selectedRelationship.value = null
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
  selectedRelationship.value = null
  if (isRelationsSet(ts) && addMode.value === 'trait') {
    // The relations set needs to know *whose* relationship before it can offer
    // traits. `addMode === 'relationship'` already knows (the sheet being viewed)
    // and keeps its two-step flow.
    addPhase.value = 'relationships'
    loadRelationships()
    return
  }
  addPhase.value = 'traits'
}

/** Where Back goes from the trait list — the relationship step, when there was one. */
const traitsBackPhase = computed(() =>
  (isRelationsSet(selectedTraitSet.value) && addMode.value === 'trait') ? 'relationships' : 'sets')

/**
 * The entity's contacts: everyone they hold a personal relationship with.
 *
 * Composed, because there is no read for "my relationship edges". Two existing
 * reads do it without a backend change, and the second is what narrows it:
 * `relatedEntities` is *undirected and unfiltered* — it returns everything joined
 * by any edge, structural ones included, so for one character it was 18 entities
 * of which most were locations and factions. `relationship`'s `type` argument
 * defaults to `relation` (the personal type), so a probe that comes back non-null
 * is exactly "I have a relationship with them".
 *
 * **`relatedEntities` has a blind spot that matters here, so it cannot be the only
 * source.** It matches `_from`/`_to` against `entities/<id>` only, so it sees
 * *entity-anchored* edges and misses every edge anchored to one of the entity's
 * **projections** — measured: Kael Drift has four relationship traits and
 * `relatedEntities(Kael)` returns **zero**. `relationship()` finds those edges
 * because it resolves endpoints through the projection path, so the settings the
 * sheet already holds are the second source: a relationship-anchored setting names
 * its contact, and those contacts are known without asking anyone. What is still
 * missing is a contact you have a *projection-anchored* relationship with but no
 * trait on yet — that needs a real read and is ticketed.
 *
 * The probes go out together: it is one burst, not a waterfall.
 */
async function loadRelationships() {
  const me = props.overrideEntityId || props.entityId
  relationshipsLoading.value = true
  relationships.value = []
  relationshipFilter.value = ''
  try {
    const data = await graphql(
      `query($id: ID!) { relatedEntities(entityId: $id) { id name type } }`, { id: me },
    )
    const peers = data?.relatedEntities || []
    const probed = await Promise.all(peers.map(async (p) => {
      const r = await graphql(
        `query($from: ID!, $to: ID!) { relationship(fromEntityId: $from, toEntityId: $to) { id } }`,
        { from: me, to: p.id },
      ).catch(() => null)
      return r?.relationship ? p : null
    }))
    const contacts = new Map(probed.filter(Boolean).map(c => [c.id, c]))

    // The blind-spot half: every contact the sheet already has a relationship
    // trait for. Type is filled in by the read below, which knows it authoritatively.
    for (const s of (allTraitSettings.value || [])) {
      if (s.fromType !== 'relationship' || !s.relationshipContactId) continue
      if (contacts.has(s.relationshipContactId)) continue
      contacts.set(s.relationshipContactId, {
        id: s.relationshipContactId,
        name: s.relationshipContactName || s.relationshipContactId,
        type: '',
      })
    }

    // One read for the rest: the type each contact actually is, and which of them
    // a player plays — `agency`'s `main` flag is what separates a main from a
    // support, and `relatedEntities` carries neither. A character with no player
    // edge has no agency at all, which is how an unclaimed one is told apart.
    const agency = new Map()
    const types = new Map()
    if (contacts.size) {
      const rows = await graphql(
        `query($ids: [ID!]!) { entities(ids: $ids) { id name type agency { main } } }`,
        { ids: [...contacts.keys()] },
      ).catch(() => null)
      for (const r of rows?.entities || []) {
        agency.set(r.id, r.agency)
        types.set(r.id, r.type)
      }
    }

    // Grouped by the order an entity list reads in — mains, then supports, then
    // everything else by type — and alphabetical inside each group, because a
    // mixed list of people, places and factions is hard to scan for a particular one.
    const accentFree = { sensitivity: 'base' }
    relationships.value = [...contacts.values()]
      .map(c => ({ ...c, type: types.get(c.id) || c.type, bucket: entityTypeBucket(types.get(c.id) || c.type, agency.get(c.id)) }))
      .sort((a, b) =>
        (entityTypeRank(a.type, agency.get(a.id)) - entityTypeRank(b.type, agency.get(b.id)))
        || String(a.name || '').localeCompare(String(b.name || ''), undefined, accentFree))
  } catch (e) {
    console.error('[sheet] add: could not load relationships', e)
  } finally {
    relationshipsLoading.value = false
  }
}

function selectRelationship(contact) {
  selectedRelationship.value = contact
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
    // A relationship trait hangs off *our* outgoing edge to this sheet, so it
    // arrives through the relationship query — the entity refresh the other path
    // uses would load the other side's settings and never show it (the relation
    // tab's rows are `relationTraits`, not the viewed entity's).
    const newRelationshipId = result.addRelationshipTrait.id
    try {
      await fetchRelationship()
      openEditorForNewTrait(newRelationshipId, { relation: true })
    } catch (e) {
      console.error('[sheet] add: refreshed but could not open the editor', e)
    }
    return
  }

  // A trait from the relations set is anchored to the *relationship*, not to the
  // entity — so it goes through `addRelationshipTrait` for the contact picked in
  // the extra step, which find-or-creates that edge.
  if (isRelationsSet(selectedTraitSet.value) && selectedRelationship.value) {
    const contact = selectedRelationship.value
    const result = await graphql(`mutation($from: ID!, $to: ID!, $traitId: ID!, $die: DieType!) {
      addRelationshipTrait(fromEntityId: $from, toEntityId: $to, traitId: $traitId, die: $die) { id }
    }`, {
      from: props.overrideEntityId || props.entityId,
      to: contact.id,
      traitId: trait.id,
      die: (trait.defaultDieType || 'd6').toUpperCase(),
    })
    if (!result?.addRelationshipTrait) {
      console.error('addRelationshipTrait failed:', error.value || 'unknown error')
      return
    }
    const newSettingId = result.addRelationshipTrait.id
    showAddTrait.value = false
    addPhase.value = 'sets'
    selectedTraitSet.value = null
    selectedRelationship.value = null
    // Relationship-anchored settings come back on the entity's own query (with
    // their contact), so this lands like any other trait add — unlike the
    // relation tab's path, which reads the *other* sheet's edge.
    try {
      await fetchEntity('add-relationship-trait')
      openEditorForNewTrait(newSettingId)
    } catch (e) {
      console.error('[sheet] add: refreshed but could not open the editor', e)
    }
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
  // Land on the trait with its editor open — the whole point of adding one from
  // the sheet is that you then set it up (dice, rating, statement), so send the
  // player straight there instead of leaving them on whatever set was showing.
  const newSettingId = result.addTraitSetting.id
  try {
    await fetchEntity('add-trait')
    openEditorForNewTrait(newSettingId)
  } catch (e) {
    // The trait is added either way — only the landing failed, so say that
    // rather than letting the editor's absence read as a broken add.
    console.error('[sheet] add: refreshed but could not open the editor', e)
  }
}

/**
 * Open the full-panel editor on a just-added trait, from wherever it landed.
 *
 * `editingTrait` resolves its id out of the lists the sheet is rendering, so
 * this must run *after* the refetch — and it is why the editor cannot be opened
 * optimistically against a setting the client has not seen yet.
 *
 * A trait whose set the universe gate excludes is added but has no row to open;
 * the console says so rather than the click looking like it did nothing.
 */
function openEditorForNewTrait(id, { relation = false } = {}) {
  if (!id) return
  const source = relation
    ? (relationTraits.value || [])
    : ((showAllTraits.value ? allTraitSettings.value : effectiveSettings.value) || [])
  const setting = source.find(t => t.id === id)
  if (!setting) {
    console.warn('[sheet] added trait is not in the visible trait lists:', id)
    return
  }
  if (relation) {
    // Where it was added from, and where its rows live.
    activeSheetView.value = 'relation'
  } else if (setting.traitsetTab === 'PROFILE') {
    activeSheetView.value = 'profile'
  } else {
    activeSheetView.value = 'traits'
    // The set it landed in is on screen: the accordion opens that section, the
    // drill-in enters it. A flat sheet has no set layer and already shows it.
    if (!flatTraitList.value) landOnSet(setting.traitsetName)
  }
  startEdit(setting)
}

// ── Trait detail (read-only) ────────────────────────────────────
// The row's third click zone. Playing the trait moved to the rating zone; the
// name / statement / empty space of the row now opens the trait read-only, with
// its full SFX, notes and tags. `contextmenu` still opens the editor.
const detailTrait = ref(null)

// Projection options with their display names resolved, for the editor's chip.
const projectionChoices = computed(() =>
  (entity.value?.projections || []).map(p => ({ id: p.id, name: p.name || universeDisplay(p.originUniverse) }))
)

// Helpers the read-only trait detail needs; functions only, so the child can
// take them as one object without any unwrapping. Playing from the detail is a
// navigation act as well as a play — the reader came here to find the trait, so
// once its die is in the pool they want the list back (B185).
const detailApi = {
  canPlayTrait, ratingTypeLabel, challengeProgressLabel, challengeRemainingGroups, detailContext,
  displayName, sfxCardModel, activateSfx,
  playTrait: async (t) => { await traitPlay.playTrait(t); backToSetList(t) },
}

// The inline trait editor's draft state + actions (see composables/useTraitEditor.js).
const {
  editingTraitId, editingTrait, availableSubtraits,
  editDice, editRatingType, editPolarity, editCapacity, editStatement, editNotes,
  editSfxIds, editIsEgo, editProjectionId, showProjectionPicker, acquirableSfxIds,
  editTags, tagSuggestions,
  editProjectionOptions, editProjectionName,
  deleteCountdown, deletingTraitId,
  startEdit, cancelEdit, onDeleteClick, doSave,
  toggleEgo, togglePolarity, toggleProjectionPicker, selectProjection, toggleSfx,
  onEditorRatingType, onEditorChange, onEditorFieldBlur,
  addSubTrait, removeSubTrait, onStatementInput, splitStatement, recoverSpentDie,
} = useTraitEditor({
  props, entity, traitSets, profileTraits, relationTraits, detailTrait, graphql,
  fetchEntity, recomputeTraitSets, recoverResourceDie, universeDisplay,
})

// Helpers the list rows call; functions only, like detailApi. It sits below the
// useTraitEditor destructure on purpose — it closes over `startEdit` (a const,
// so creating the object earlier would hit the TDZ).
const traitRowApi = {
  isKnown, isInPool, isOffered, displayName, traitTimerLabel, isResourceDepleted,
  traitDiceGroups, resourceDiceGroups, resourceSpentGroups, challengeRemainingGroups,
  spendResourceGroup: traitPlay.spendResourceGroup, spendChallengeGroup: traitPlay.spendChallengeGroup, challengeProgressLabel,
  resolvedDieType, resourceDisplay, sfxCardModel, activateSfx,
  openTraitDetail, startEdit, playTrait: traitPlay.playTrait, onTouchStart, onTouchEnd,
  isContainer, isExpanded, toggleExpand, containerCount, hasContents,
  onTraitDragStart, onGripTouchStart, onTraitDragOver, onTraitDragLeave, onTraitDrop, onTraitDragEnd,
  isDragOver, isDragging, clickSuppressed, canDrag,
}

function openTraitDetail(t) {
  // A touch long-press fires startEdit on touchstart and the click on release,
  // so the editor can already be open by the time this runs — don't stack the
  // detail panel behind it.
  if (editingTraitId.value) return
  detailTrait.value = t
}

// ── Changing a trait instance's definition ──────────────────────
// The candidate definitions for the instance being edited, and the repoint
// itself. Kept in the sheet (not the panel) because both need the entity's
// universe and the entity refresh — the panel is deliberately presentational.
const definitionOptions = ref(null)
const definitionPending = ref(false)
// Open/closed and the filter text are the sheet's, not the panel's — the panel
// is re-created whenever the sheet re-renders, which is exactly what happens
// when the option list arrives. Held in the panel, the first click opened the
// list and the re-render wiped it, so the dropdown never appeared. Same reason
// `showProjectionPicker` lives in `useTraitEditor`.
const showDefinitionPicker = ref(false)
const definitionFilter = ref('')
// The trait sets the candidates live in — `[{ id, name }]`, narrowed to sets that
// actually hold one. `null` on the filter means "the instance's own set": the
// panel derives the default from the trait rather than this holding an id that
// would have to be kept in step with it.
const definitionTraitsets = ref([])
const definitionTraitsetFilter = ref(null)

// A different instance may hold different things already, so the candidate list
// is per-instance: drop it when the editor moves to another trait rather than
// reusing a list built for the one before.
watch(editingTraitId, () => {
  definitionOptions.value = null
  definitionTraitsets.value = []
  definitionTraitsetFilter.value = null
  showDefinitionPicker.value = false
  definitionFilter.value = ''
})

/** Open or close the definition list, loading its options the first time. */
function toggleDefinitionPicker() {
  showDefinitionPicker.value = !showDefinitionPicker.value
  definitionFilter.value = ''
  // Each open starts on the trait's own set, which is the answer most of the
  // time — a repoint within a set is the common case, and the set is what the
  // player recognises the trait by.
  definitionTraitsetFilter.value = null
  if (showDefinitionPicker.value) fetchDefinitionOptions()
}

/**
 * What this instance could become.
 *
 * Scoped to the entity's current universe, like the add-trait picker — a
 * definition from another universe is not one this body can hold. Two filters,
 * both mirroring rules the write path enforces (``services/trait_change``), so
 * the list never offers a change that would be refused: a container may only
 * become another container, and a definition the entity already holds is a
 * collision **only in a set that forbids duplicates** — a set that allows them
 * holds any number of one definition, statement or no statement. Reading the
 * second filter as "already held anywhere" (or as "held under this statement")
 * hid the whole point of such a set from the control (reported 2026-09-25 on
 * `resources`).
 *
 * ``tags`` must be selected here: ``isContainer`` reads them, and a query that
 * omitted them would make every candidate look like a non-container — which
 * passes by accident for an ordinary trait and empties the list for a container.
 * ``allowDuplicates`` likewise: without it every candidate set would read as
 * one-per-trait and the filter would be wrong in the other direction.
 */
async function fetchDefinitionOptions() {
  if (definitionOptions.value) return
  const t = editingTrait.value
  if (!t) return
  const u = entity.value?.currentUniverse || props.universe
  const [data, setData] = await Promise.all([
    graphql(`query($u: String!) { traitsByUniverse(universe: $u) { id name traitsetId tags } }`, { u }),
    // The set *names* and their order, and `allowDuplicates` — the candidate's set
    // is what decides whether a definition it already holds is a collision. The
    // whole registry rather than `traitsetsByUniverse`: a trait can sit in a set
    // that universe does not list (25 of 36 sets, in three_realms), and then the
    // filter would label it with a raw id.
    graphql(`query { traitsets { id name order allowDuplicates } }`),
  ])
  const sets = new Map((setData?.traitsets || []).map(s => [s.id, s]))
  const orderOf = (id) => sets.get(id)?.order ?? 999

  // The definitions the entity already holds. The edited instance is excluded: it
  // is not a collision with itself, and the list marks it selected below.
  const held = new Set()
  for (const s of ((showAllTraits.value ? allTraitSettings.value : effectiveSettings.value) || [])) {
    if (s.id === t.id) continue
    held.add(s.traitId)
  }

  /**
   * Whether repointing at `o` would be refused as a twin.
   *
   * **The write path's rule, mirrored** — `repoint_trait_setting` →
   * `_refuse_collision` → `may_hold_another` — not a rule of this control's own:
   * a set that allows duplicates permits any number of one definition, so a held
   * definition is not a collision there at all; a set that forbids them collides
   * on any instance. Note it asks the **candidate's** set, not the instance's: a
   * repoint moves the instance into the new definition's set, and that is the set
   * whose rule the write path applies.
   */
  const wouldCollide = (o) => held.has(o.id) && !sets.get(o.traitsetId)?.allowDuplicates

  const wantContainer = isContainer(t)
  definitionOptions.value = (data?.traitsByUniverse || [])
    // The instance's *own* definition is always offered, even when the entity
    // holds another instance of it: it is where the player is, and the list marks
    // it selected so the control never reads as a dead end. Choosing it is a
    // no-op, not a mutation.
    .filter(o => isContainer(o) === wantContainer
      && (o.id === t.traitId || !wouldCollide(o)))

  // The sets to offer are the ones the candidates actually landed in, so the
  // filter can never send the player to an empty list. Ordered as the sheet
  // orders its own sets, so the picker's list and the sheet's agree.
  definitionTraitsets.value = [...new Set(definitionOptions.value.map(o => o.traitsetId))]
    .map(id => ({ id, name: sets.get(id)?.name || id }))
    .sort((a, b) => (orderOf(a.id) - orderOf(b.id)) || a.name.localeCompare(b.name))
}

/** Repoint the edited instance at another definition, keeping it open. */
async function changeDefinition(traitId) {
  const t = editingTrait.value
  if (!t || !traitId || definitionPending.value) return
  definitionPending.value = true
  try {
    const result = await graphql(`mutation($id: ID!, $traitId: ID!) {
      updateTraitSetting(id: $id, input: { traitId: $traitId }) { id traitId traitsetId }
    }`, { id: t.id, traitId })
    if (!result?.updateTraitSetting) {
      console.error('[sheet] change definition failed:', error.value || 'unknown error')
      return
    }
    definitionOptions.value = null
    definitionTraitsets.value = []
    showDefinitionPicker.value = false
    definitionFilter.value = ''
    definitionTraitsetFilter.value = null
    // The instance keeps its id, so re-open the same one — the panel remounts
    // with the new name, set and possible SFX/sub-traits, and `startEdit`
    // re-seeds every draft field from it.
    await fetchEntity('change-definition')
    await nextTick()
    openEditorForNewTrait(t.id)
  } catch (e) {
    console.error('[sheet] change definition failed:', e)
  } finally {
    definitionPending.value = false
  }
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

// Same gates the play applies, via `useTraitPlay` — the detail only offers the play
// affordance when playing would actually do something. An EMPTY (profile) or depleted
// trait has no die to play, so it gets no hint and no sub-trait play button.
function canPlayTrait(t) {
  if (!traitPlay.canPlay(t)) return false
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
  if (timer) {
    rows.push({ label: 're-enables', value: timer })
    const origin = traitTimerOrigin(t)
    if (origin) rows.push({ label: 'from', value: origin })
  }
  return rows
}

// ── Playing a trait (rating zone) ───────────────────

// A trait and its sub-traits are ONE pool pick: `countSetPicks` counts the
// subtree once, so the set limit is satisfied by whichever member you touch.
// The old app completed the group from either end and this keeps that:
//
//   - playing a **sub-trait** pulls its ancestor chain in, so the pick is whole
//     (`click_subtrait` → `play_trait()` on the parent);
//   - playing a trait also pushes the **negative** sub-traits it carries — in a
//     contest those route to the opposition (`DiceRoller.addFromSheet`);
//   - removing a trait clears its whole subtree, so no orphan dice linger
//     (the old `remove_traitsetting_dice` loop over subtraits).
//
// Only **static** negative children ride along automatically: a resource or
// challenge sub-trait is *spent*, and spending is the player's deliberate act,
// not a side effect of playing its parent.
// The graph walks (`ancestorsOf` / `descendantsOf` / `carriedNegatives`) live in
// utils/traitTree.js with the rest of the group semantics.
function settingSearchSpace() {
  return [...(effectiveSettings.value || []), ...(allTraitSettings.value || [])]
}

// The negative sub-traits a trait carries when it is played. `skipId` is the
// trait whose own dice the play is about to push: without it, playing a
// negative sub-trait would push it once here and once there, and the dice
// layer's toggle would add then immediately remove it.
function playBaggage(t, skipId = null) {
  for (const child of carriedNegatives(t)) {
    if (child.id === skipId) continue
    if (child.enabled === false || isInPool(child)) continue
    traitPlay.contribute(child)
  }
}

// The related members of `t`'s group. The clicked trait's own dice are handled
// by the play; this only completes (or dismantles) the group around it.
function cascadeGroup(t) {
  if (isInPool(t)) {
    // Removing a trait takes its subtree out of the pool, and the group's
    // negative baggage back out of whatever pool it was routed to. A
    // complication must not outlive the trait that carried it.
    for (const child of descendantsOf(t)) {
      if (isInPool(child)) emit('removeByTsId', child.id)
    }
    for (const member of [t, ...descendantsOf(t)]) {
      for (const carried of carriedNegatives(member)) {
        if (!isOffered(carried)) continue
        emit('retractNegative', {
          tsId: carried.id, source: carried.name, label: displayName(carried.name),
        })
      }
    }
    return
  }
  // Playing a sub-trait completes its pick: bring the ancestors in first.
  // A resource or challenge ancestor is *spent*, not played, so it is left
  // alone — its own row click owns that decision.
  for (const ancestor of ancestorsOf(t, settingSearchSpace())) {
    if (ancestor.ratingType === 'RESOURCE' || ancestor.ratingType === 'CHALLENGE') continue
    if (isInPool(ancestor) || !canPlayTrait(ancestor)) continue
    traitPlay.contribute(ancestor)
    playBaggage(ancestor, t.id)
  }
  playBaggage(t, t.id)
}

// (Playing a trait — its gates, its group cascade's payloads, the single-vs-mixed
// die-type split and the two spends — is `useTraitPlay`, shared with the map's trait
// chips. The sheet supplies the pool bookkeeping above and nothing else.)

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

// A challenge pool's unfilled capacity, rendered as ghost dice beside the dice
// that have filled it (see challengeRemaining in utils/traitTree.js).
function challengeRemainingGroups(t) {
  return groupByDieType(challengeRemaining(t))
}

function isResourceDepleted(t) {
  // Resources and challenge pools show a dimmed "depleted/empty" state when
  // their spendable dice ledger is empty.
  if (t.ratingType !== 'RESOURCE' && t.ratingType !== 'CHALLENGE') return false
  if ((t.dice || []).length) return false
  // An unfilled challenge track is not depleted — it is *waiting*, and its
  // ghost dice say so. Only a challenge with no track at all reads as depleted;
  // for a resource, an empty ledger is exactly what depleted means.
  if (t.ratingType === 'CHALLENGE') return !(t.capacity || []).length
  return true
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
  // Must agree with `limitReachedFor`: a sub-trait rides its parent, so
  // the subtree counts once however many of its members are in the pool.
  return countSetPicks(ts.traits, isInPool)
}

function sfxAllowedInPhase(sfxId) {
  const allowed = SFX_PHASES[sfxId] || ['adding']
  return allowed.includes(props.phase)
}

// Pool state tracking — called by DiceRoller via App
function setPoolSources(sources) {
  // sources is now [{ die, label, tsId }, ...] — track by tsId
  poolSources.value = sources.map(s => s.tsId).filter(Boolean)

  // A set that has just filled its limit hands the reader the next one. This is
  // the moment the count is truthful — see `advanceToNextSetIfFull`.
  advanceToNextSetIfFull()

  // Auto-recover dice that were removed from the pool before rolling
  // (e.g. via chip click in DiceRoller).  Only during adding phase —
  // once dice are rolled they stay spent.  A resource die returns through its
  // spent ledger; a challenge die is refunded outright (no ledger).
  if (props.phase !== 'adding') return
  let recovered = false
  for (const tsId of Object.keys(refundableSpends.value)) {
    const poolDice = sources.filter(s => s.tsId === tsId).map(s => s.die)
    const { keep, refunds } = splitRefunds(refundableSpends.value[tsId], poolDice)
    for (const entry of refunds) {
      if (entry.kind === 'challenge') recoverChallengeDie(tsId, entry.die)
      else recoverResourceDie(tsId, entry.die)
      recovered = true
    }
    if (keep.length) refundableSpends.value[tsId] = keep
    else delete refundableSpends.value[tsId]
  }
  if (recovered) fetchEntity('pool-dice-refunded')
}

defineExpose({ resetSfxCounts, setPoolSources, setRazmerit, setOfferedTraits, fetchEntity, fetchInFlightSfxIds, clearSfxActivations, fetchTimers, refreshBlueBook: () => blueBookRef.value?.refresh() })

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

// A roll-table-as-menu SFX carries a single roll_table/menu effect whose table is
// a **reference** (`refs.table`) — see `utils/rollTableMenu.js`.

// A condition-blocked SFX is owned (it appears on the sheet) but its static
// conditions (e.g. source_rating, entity_type) fail at this moment, so it can't
// fire. ``null`` means availability hasn't loaded yet (don't block optimistically).
function sfxConditionBlocked(sfxId) {
  if (availableSfxIds.value == null) return false
  return !availableSfxIds.value.includes(sfxId)
}

function sfxTitle(sfxId) {
  if (sfxConditionBlocked(sfxId)) {
    // The server's phrases carry an `unmet:` prefix so they cannot read as the
    // condition itself; the title supplies its own framing, so it is dropped here.
    const detail = (sfxUnmetReasons.value[String(sfxId)] || [])
      .map((r) => String(r).replace(/^unmet:\s*/, '')).join('; ')
    return detail
      ? `${sfxName(sfxId)} (conditions not met: ${detail})`
      : `${sfxName(sfxId)} (conditions not met)`
  }
  return sfxActive(sfxId) ? `Deactivate ${sfxName(sfxId)}` : `Activate ${sfxName(sfxId)}`
}

// Everything one SFX card needs, resolved once for all five strips (entity,
// projection, trait row, detail, trait-set). `disabled` reproduces the old
// inline guard so the card does not fire when the phase or a condition blocks.
// One SFX in a card strip. Where the card sits decides how much it earns:
//   'chip' — the trait teaser: the name, nothing else;
//   'card' — the entity / projection / trait-set strips: name + description;
//   'full' — the trait detail clickthrough: + the natural-language rules text
//            (the "translation" belongs in the drill-in, not in the teaser).
function sfxCardModel(sfxId, variant = 'card') {
  const blocked = sfxConditionBlocked(sfxId)
  return {
    name: sfxName(sfxId),
    description: variant === 'chip' ? '' : sfxDescription(sfxId),
    rules: variant === 'full' ? sfxCardText(sfxId) : '',
    title: sfxTitle(sfxId),
    active: sfxActive(sfxId),
    used: sfxUsed(sfxId),
    blocked,
    disabled: blocked || !sfxAllowedInPhase(sfxId),
  }
}

async function fetchAvailableSfxIds() {
  const id = props.overrideEntityId || props.entityId
  if (!id) { availableSfxIds.value = null; return }
  const e = epoch()
  try {
    const data = await graphql(
      `query($id: ID!, $u: String!) { availableSfxIds(entityId: $id, universe: $u) }`,
      { id, u: props.universe },
    )
    if (stale(e)) return
    availableSfxIds.value = (data?.availableSfxIds || []).map(String)
    await fetchSfxUnmetReasons(id)
  } catch (err) {
    console.error('fetchAvailableSfxIds', err)
    if (stale(e)) return
    availableSfxIds.value = null
    sfxUnmetReasons.value = {}
  }
}

// The *why* behind a greyed card. Asked for the rules the sheet can render, so the
// answer is only about what is on screen.
async function fetchSfxUnmetReasons(entityId) {
  const ids = Object.keys(sfxCatalog.value || {})
  if (!entityId || !ids.length) { sfxUnmetReasons.value = {}; return }
  const e = epoch()
  try {
    const data = await graphql(
      `query($id: ID!, $u: String!, $ids: [ID!]) {
         unavailableSfx(entityId: $id, universe: $u, sfxIds: $ids) { sfxId reasons }
       }`,
      { id: entityId, u: props.universe, ids },
    )
    if (stale(e)) return
    const map = {}
    for (const row of data?.unavailableSfx || []) map[String(row.sfxId)] = row.reasons || []
    sfxUnmetReasons.value = map
  } catch (err) {
    console.error('fetchSfxUnmetReasons', err)
    if (stale(e)) return
    sfxUnmetReasons.value = {}
  }
}

/**
 * Rules this entity has activated and not yet committed — the server's truth for
 * the chips' take-back state, so it survives a reload (a client-side flag would
 * forget, and the next press would re-apply instead of ending). A rule the
 * server no longer lists has ended — taken back, or its cost left the pool — so
 * its optimistic flag is cleared here rather than left to lie.
 *
 * The same round trip reads the balance: a pool save is exactly the moment a
 * rule's cost can leave, and the refund lands on the server as part of handling
 * that save — so the sheet refreshes the ledger from the server at that moment
 * instead of waiting on a push.
 */
/** Clear the optimistic 'active' flags for rules the caller has just taken back.
 *
 * `fetchInFlightSfxIds` cannot do this, and that is the whole bug: it clears a
 * rule only when the server had **previously** reported it in flight
 * (`seededInFlight`), and a manual rule that applies nothing before its first
 * choice ([[sfx-gift]]) is never in that set — so the chip its press lit stayed
 * lit, through every refresh, until a reload. The caller's cancel path knows
 * exactly which rules it just ended, so it says so (the human, 2026-09-29).
 */
function clearSfxActivations(sfxIds) {
  for (const sfxId of sfxIds || []) {
    if (!sfxId) continue
    sfxActivations.value[sfxId] = 0
    seededInFlight.value.delete(sfxId)
  }
}

async function fetchInFlightSfxIds(reason = 'unspecified') {
  const id = props.overrideEntityId || props.entityId
  if (!id) return
  const e = epoch()
  _stampFetch('in-flight-sfx-fetch', reason)
  try {
    const data = await graphql(
      `query($id: ID!) { inFlightSfxIds(entityId: $id) entity(id: $id) { razmerit } }`,
      { id },
    )
    if (stale(e)) return
    const ids = (data?.inFlightSfxIds || []).map(String)
    for (const sfxId of seededInFlight.value) {
      if (!ids.includes(sfxId)) sfxActivations.value[sfxId] = 0
    }
    for (const sfxId of ids) {
      sfxActivations.value[sfxId] = 1
    }
    seededInFlight.value = new Set(ids)
    const balance = data?.entity?.razmerit
    if (balance != null) setRazmerit(balance, id)
  } catch (e) {
    console.error('fetchInFlightSfxIds', e)
  }
}

async function fetchPlaceSfxRules() {
  const id = props.overrideEntityId || props.entityId
  if (!id) { placeRuleGroups.value = []; return }
  const e = epoch()
  try {
    const data = await graphql(
      `query($id: ID!, $u: String!) { placeSfxRules(entityId: $id, universe: $u) { locationId locationName sfxIds } }`,
      { id, u: props.universe },
    )
    if (stale(e)) return
    placeRuleGroups.value = data?.placeSfxRules || []
  } catch (err) {
    console.error('fetchPlaceSfxRules', err)
    if (stale(e)) return
    placeRuleGroups.value = []
  }
}

// A place's rule wears the same card as the entity's own, with one difference:
// a rule that fires on its own when the world moves isn't something you press,
// so it reads its rules line and stays inert instead of looking like a button.
// `readonly` rather than `blocked`: it is not a control that is unavailable, it
// is a statement — and the dimming `blocked` carries made the name unreadable,
// which is the one thing a reader wants from it (B189).
function placeCardModel(sfxId) {
  const trigger = sfxCatalog.value[sfxId]?.trigger
  if (trigger && trigger !== 'manual') {
    return { ...sfxCardModel(sfxId, 'full'), readonly: true, title: 'Fires by itself.' }
  }
  return sfxCardModel(sfxId)
}

async function fetchSfxCatalog() {
  try {
    const r = await fetch('/api/v1/graphql', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: `query { sfxs { id name description trigger cardText effects { timing type action target entity result refs } } }` }),
    })
    const json = await r.json()
    const map = {}
    for (const s of json?.data?.sfxs || []) map[s.id] = s
    sfxCatalog.value = map
    // The reasons are asked for *these* rules, so the catalog has to be in hand
    // first; whichever fetch finishes last refreshes them.
    const id = props.overrideEntityId || props.entityId
    if (id && availableSfxIds.value != null) await fetchSfxUnmetReasons(id)
  } catch (e) {
    console.error('fetchSfxCatalog', e)
  }
}

function resetSfxCounts() {
  sfxActivations.value = {}
  refundableSpends.value = {}
}

// ── The GM's own rules, and the surface that presses them ────────────
// A GM-owned rule is run against **the scene**: the roaming GM has no acting
// entity, and the place is what "do this here" means. A rule that needs a
// particular character asks for one — that question arrives on the same wizard
// the sheet already hosts, which is why the question host is part of this
// surface rather than a second mechanism.
const sfxSubjectId = computed(() => props.entityId || props.placeId)

async function fetchGmRules() {
  if (!props.gmMode) { gmSfxIds.value = []; return }
  try {
    const data = await graphql(`query { sfxOwners(ownerType: GM) { sfxIds } }`)
    gmSfxIds.value = (data?.sfxOwners || []).flatMap((o) => o.sfxIds || [])
  } catch (e) {
    console.error('fetchGmRules', e)
    gmSfxIds.value = []
  }
}

// One card per rule that lives on the GM. A **manual** rule is a press; anything
// else fires from the roller menu or from a state change, so it is *stated*
// rather than offered — the same `readonly` axis the auto-firing rules already
// use, and the reason the author's ask was specifically for the manual ones.
const gmRuleCards = computed(() => gmSfxIds.value.map((id) => {
  const model = sfxCardModel(id)
  const trigger = sfxCatalog.value[id]?.trigger || ''
  if (trigger === 'manual') return { id, model }
  const from = trigger === 'menu' ? 'the roller menu' : `the ${trigger.replace(/_/g, ' ')} trigger`
  return { id, model: { ...model, readonly: true, title: `${sfxName(id)} — fires from ${from}.` } }
}))

function activateGmRule(sfxId) {
  if (!sfxSubjectId.value) return
  return activateSfx(sfxId, null, sfxSubjectId.value)
}

// The play surface's own data. Both reads are shared: the roster is the same
// `entities(type: null)` list the GM panel holds, and the tree is a module-level
// singleton — so a roaming GM whose panel was never opened still gets both. The
// tree composable is called with no arguments because only its *singleton* is
// wanted here: `fetchLocationTree` and `locationTree` are state-free reads, and
// the focus-filter wiring belongs to the panel.
const { entities: sceneEntities, fetchEntities } = useEntityCrud()
const { locationTree, fetchLocationTree } = useLocationTree({})

// Asked for **only when the play surface is the body** (a GM acting as nobody): a
// GM who is acting as an entity gets that entity's sheet, and would otherwise pay
// for a ~1k-row roster query to draw something it does not render.
async function loadGmSurface() {
  if (!props.gmMode || props.entityId || props.overrideEntityId) return
  await Promise.all([fetchEntities(), fetchLocationTree(), fetchGmRules()])
}

const QUERY = `
  # Every trait-setting field, shared by all levels of the tree. A nested trait
  # opens the same detail panel and the same editor as a top-level one, and can
  # itself be a container — so it needs the same field set, not a subset.
  fragment TraitNode on TraitSetting {
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
    # Rules this instance *has* without carrying them, from a rule's granted reach
    # ([[Dynamic SFX Reach]]). Read-time, and separate from sfxIds on purpose:
    # that list is what is attached and the trait editor writes it back whole.
    grantedSfxIds
    universe
    dice
    spentDice
    capacity
    polarity
    enabled
    # The author's position among siblings, read at every depth. An *ordered*
    # container numbers its rows from it; the reads already sort children by it,
    # so a query that omitted the field would leave the numbering blank while the
    # rows still looked sorted — the quietest way for this to be wrong.
    order
    traitsetOrder
    traitsetLimit
    traitsetTab
    knownTo
    possibleSfxIds
    tags
    registryTags
    relationshipContactId
    relationshipContactName
    relationshipContactType
    relationshipType
    possibleSubtraitIds
    parentTraitsettingId
    # The picture travels with the setting at every depth, like the rest of the
    # field set: a nested row opens the same detail panel as a top-level one.
    sheetImage: image(role: "sheet")
    backgroundImage: image(role: "background")
    imageTransparent
  }
  # GraphQL requires every nesting level spelled out, so the chain is linear and
  # each link adds exactly one level: Depth2 = 2 levels, Depth3 = 3. The sheet
  # asks for QUERY_DEPTH (4) in total — a top-level trait plus three. Keep this
  # in step with QUERY_DEPTH in utils/traitTree.js.
  fragment TraitNodeDepth2 on TraitSetting {
    ...TraitNode
    subTraitSettings { ...TraitNode }
  }
  fragment TraitNodeDepth3 on TraitSetting {
    ...TraitNode
    subTraitSettings { ...TraitNodeDepth2 }
  }

  query($id: ID!) {
    entity(id: $id) {
      id
      type
      name
      razmerit
      currentUniverse
      currentLocation
      currentProjection
      backgroundImage
      backgroundRoleImage: image(role: "background")
      sheetPortrait
      sheetPortraitTransparent
      sfxIds
      # What this entity *has* without carrying it ([[Dynamic SFX Reach]]): a granted
      # reach declaration yields it as an owner, and nothing is attached, so sfxIds
      # alone can never show such a rule. Requested here so the plumbing is ready;
      # how the sheet draws it is the sheet's call. (No backticks in here: this is a
      # JS template literal, and one would end the query.)
      grantedSfxIds
      projections {
        id originUniverse universe name sheetImage sheetImageTransparent currentLocation transversalType sfxIds grantedSfxIds
      }
      traitSetSettings {
        id traitsetId sfxIds grantedSfxIds
      }
      traitSettings {
        ...TraitNode
        subTraitSettings { ...TraitNodeDepth3 }
      }
      effectiveTraitSettings {
        ...TraitNode
        subTraitSettings { ...TraitNodeDepth3 }
      }
    }
  }
`

// ── Fetch attribution (temporary diagnostic) ─────────────────────────────
// Symptom under investigation: adding a trait to the pool makes the *next* set
// appear to reload. useApi already logs every GraphQL call, but not *why* it
// fired — so each fetch is stamped with the caller that asked for it, numbered
// per kind, and flagged when a second one lands inside the same interaction.
// Console-only; strip this block and the reason arguments once the cause is
// fixed and the paths are quiet again.
const _fetchLog = {}
// ── The perspective epoch ────────────────────────────────────────────
// Every per-entity read outlives the perspective that started it, and each one
// writes component state when it lands: the condition-filtered SFX list (what
// greys a card whose conditions do not hold), the unmet reasons, the place's
// rules, the timer line, the activation ledger. A perspective can be **dropped**
// between the request and its answer — a GM going back to roaming is the case
// that bit (the author, 2026-09-29) — and a late write re-installs exactly what
// `releaseEntity` cleared. Measured rather than reasoned: the play surface came
// up with the GM's own rule cards greyed and unpressable, because the previous
// entity's availability list landed *after* the release that was meant to clear
// it. One counter, bumped whenever the perspective moves, and each read drops an
// answer that is no longer the current one — cheaper and far more honest than
// teaching every reader to distrust the state.
let perspectiveEpoch = 0
const epoch = () => perspectiveEpoch
const stale = (e) => e !== perspectiveEpoch

function _stampFetch(kind, reason) {
  const now = performance.now()
  const s = _fetchLog[kind] || (_fetchLog[kind] = { n: 0, lastAt: 0 })
  const gap = s.lastAt ? Math.round(now - s.lastAt) : null
  s.n += 1
  s.lastAt = now
  const repeat = gap !== null && gap < 1500
  console.log(`[diag] ${kind} #${s.n} reason=${reason}${gap === null ? '' : ` gap=${gap}ms`}${repeat ? '   <<< fires again inside one interaction' : ''}`)
  if (repeat) {
    const chain = (new Error().stack || '').split('\n').slice(2, 6).map(l => l.trim()).join('  <-  ')
    console.log(`[diag] ${kind} #${s.n} caller chain: ${chain}`)
  }
  perfMark(kind, { reason, n: s.n, gap })
}

async function fetchEntity(reason = 'unspecified') {
  const id = shownEntityId.value
  if (!id) return
  const e = epoch()
  _stampFetch('entity-fetch', reason)
  const data = await graphql(QUERY, { id })
  // A response that settles after the perspective moved would re-install the
  // entity the release just cleared; whoever holds the new perspective owns
  // loading it.
  if (stale(e)) return
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
  // The perspective is moving: anything already in flight is now about somebody
  // else and must not write when it lands.
  perspectiveEpoch++
  const id = shownEntityId.value
  // No id at all: the sheet has no entity to draw. Returning here used to leave
  // the **previous** entity in place, so a GM who stopped acting as someone kept
  // that character's sheet on screen — `hasEntity` stayed true and the branch
  // below it (the roaming GM's play surface) was never reached. A perspective can
  // be dropped without another being taken up, so this has to be a transition of
  // its own (the author, 2026-09-29).
  //
  // The gate above is now derived from this same value, so the two cannot
  // disagree: the branch flips the moment the perspective does, and this keeps
  // the state behind it truthful.
  if (!id) { releaseEntity(); return }
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
  const promise = fetchEntity('cache-miss')
  inflightLoad = { id, promise }
  promise.finally(() => {
    if (inflightLoad && inflightLoad.id === id) inflightLoad = null
  })
}

// Let go of the entity and of everything derived from it. The per-entity caches
// go with it, and two of them are load-bearing rather than tidy:
// `availableSfxIds` is what greys a card whose conditions do not hold, so the
// previous entity's list would grey the GM's own rules on the play surface —
// `null` means "not loaded, do not block optimistically"; and the activation
// counts (`resetSfxCounts`) belong to the entity that earned them. The rest is
// what the entity branch renders, so leaving it would show a character's traits
// again the instant a new entity arrived with a partial payload.
function releaseEntity() {
  entity.value = null
  allTraitSettings.value = []
  effectiveSettings.value = []
  placeRuleGroups.value = []
  sfxUnmetReasons.value = {}
  availableSfxIds.value = null
  resetSfxCounts()
  recomputeTraitSets('entity-released')
}

function applyEntity(e) {
  entity.value = e
  resolveNames(e)
  allTraitSettings.value = e.traitSettings || []
  effectiveSettings.value = e.effectiveTraitSettings || []
  recomputeTraitSets('entity-applied')
  fetchTimers()
  fetchAvailableSfxIds()
  fetchInFlightSfxIds()
  fetchPlaceSfxRules()
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

// `subjectId` overrides what the rule is run **against**, which is normally the
// sheet's own entity. The one other case is a GM-owned rule pressed from the
// roaming GM's play surface: there is no acting entity, so the scene stands in.
//
// Answering a question, and the one kind whose answer **is** the thing asked for:
// a roll-table menu whose table is named by a **path**. That effect has no applier
// — the client is the actor — so without opening it here the answer resolved to a
// table id and then went nowhere, which is exactly "the table doesn't appear".
// Every other answer is passed up as before.
function onChoiceResolved(resolutions) {
  for (const r of resolutions || []) {
    const tableId = rollTableIdFromAnswer(r)
    if (!tableId) continue
    const sfxId = r.sourceSfxId || ''
    rollTableMenu.value = { sfxId, tableId, name: sfxId ? sfxName(sfxId) : 'Roll Table', mode: 'apply' }
    break
  }
  emit('sfx-choice-answer', resolutions)
}

async function activateSfx(sfxId, sourceId = null, subjectId = null) {
  const subject = subjectId || props.entityId
  const menu = rollTableMenuEffect(sfxCatalog.value[sfxId])
  if (menu) {
    const isSupportCast = sfxId === 'sfx-roll-support-cast'
    let tableId = rollTableIdOf(menu)
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
    if (tableId) {
      rollTableMenu.value = {
        sfxId, tableId, name: sfxName(sfxId),
        mode: isSupportCast && props.playerId && props.mainEntityId
          ? 'create-support' : 'apply',
      }
      return
    }
    // No literal table: `refs.table` is a **path**, so the engine names the table
    // by asking. Fire it and let `onChoiceResolved` open the menu with the answer
    // — reading the emptied positional `target` here instead is what made every
    // menu rule, including this one, open nothing at all.
    await triggerSfx(subject, sfxId, props.universe, {
      phase: props.phase, ...(sourceId ? { source_id: sourceId } : {}),
    })
    return
  }

  const active = sfxActive(sfxId)

  if (!active) {
    // Activate. If the SFX declares a source kind, pass the surface it was
    // clicked from (the trait instance id) as ``source_id`` so the backend
    // binds it to the declared ``{variable}``.
    await triggerSfx(subject, sfxId, props.universe, { phase: props.phase, ...(sourceId ? { source_id: sourceId } : {}) })
    sfxActivations.value[sfxId] = 1
    // Re-stamp dice already in the pool (armed after adding).
    const tsId = findTsIdForSfx(sfxId)
    if (tsId) emit('stampSfx', { tsId, sfxId })
    await fetchEntity('sfx-activate')

    if (sfxId === 'sfx-hinder') {
      const tsId = findTsIdForSfx('sfx-hinder')
      emit('removeByTsId', tsId)
      // Stamp the die with the rule that put it there: the pool is the ledger, so
      // taking this die back out is how the Hinder is taken back.
      emit('addToPool', { die: 'd4', source: 'hinder', label: 'Hinder d4', tsId, armedSfxIds: [sfxId] })
    }
    if (sfxId === 'sfx-spray-n-pray') {
      emit('splitDie', { source: 'shooting', label: 'Spray' })
    }
    emit('sfxToggled', { sfxId, active: true })
  } else {
    // Deactivate (reverse)
    sfxActivations.value[sfxId] = 0

    // Take back the activation: every undo it still owes is applied now (the
    // razmerit it earned, the die it added), and what was still waiting on a
    // roll is dropped. A rule with nothing in flight is a no-op here.
    await endSfx(subject, sfxId)

    // The take-back above (`endSfx`) already refunded what this rule earned or
    // spent — the legacy `{reverse: true}` call would have reversed the same
    // money a second time. What is left here is the pool edit.
    if (sfxId === 'sfx-hinder') {
      emit('removeByTsId', findTsIdForSfx('sfx-hinder'))
    }
    if (sfxId === 'sfx-spray-n-pray') {
      emit('removeFromPool', 'shooting-a')
      emit('removeFromPool', 'shooting-b')
    }
    emit('sfxToggled', { sfxId, active: false })
    await fetchEntity('sfx-end')
  }
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
    return true
  }
  return false
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
  if (e.key !== 'Escape') return
  if (portraitViewerOpen.value) { portraitViewerOpen.value = false; return }
  if (editingTraitId.value) cancelEdit()
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
  loadGmSurface()
})
watch(() => [props.gmMode, props.entityId, props.overrideEntityId], loadGmSurface)
watch(() => props.entityId, loadCachedEntity)
watch(() => props.universe, loadCachedEntity)
watch(() => props.overrideEntityId, loadCachedEntity)
watch(showAllTraits, () => recomputeTraitSets('show-all-toggled'))

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
        relationTraits { ${RELATION_TRAIT_FIELDS} }
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
/* The sheet's own choice table — the sheet body while a question is open, the
   same way the life path's is. It therefore takes the body-scroll idiom every
   other sheet view uses (`.sheet-scroll`), and adds nothing else: the wizard is
   `embedded`, so it draws no card here, exactly as the life path's `ChoiceTable`
   has none in this same panel.

   It used to be an absolutely-positioned card at `right/bottom: 12px`,
   `z-index: 40`, `max-height: 70%`. Two things were wrong with that. It claimed
   to leave the raising trait readable behind it, but its own background is
   `--overlay-2` — two percent opaque — so the rows showed *through* it and the
   question was unreadable over its own context. And a question you must answer
   before the effect lands is a step, not a footnote: floating it made the sheet
   look unchanged, as if the click had done nothing. */
.sheet-sfx-choice {
  flex: 1;
  overflow-y: auto; overflow-x: hidden;
}
/* The embedded roll table fills the slot and scrolls its *rows*: the slot's own
   scrollbar plus the card's was two on a phone, and the card is not a card here.
   The question wizard beside it keeps the slot's scroll — it is bounded by its
   own candidates list and reads better scrolling with the panel. */
.sheet-roll-table {
  display: flex; flex-direction: column;
  min-height: 0; overflow: hidden;
}

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

/* Portrait is a control: click (or Enter/Space) opens the viewer modal. */
.sheet-portrait.clickable { cursor: pointer; transition: border-color 0.15s ease; }
.sheet-portrait.clickable:hover { border-color: var(--accent); }
.sheet-portrait.clickable:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

/* Portrait viewer modal (teleported to body, like the roll-table menu). */
.portrait-viewer-overlay {
  position: fixed; inset: 0; z-index: 600;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,0.65);
}
.portrait-viewer {
  display: flex; flex-direction: column; gap: 6px;
  max-width: min(92vw, 900px); max-height: 90vh; padding: 8px;
  background: var(--bg-panel-solid);
  border: 1px solid var(--overlay-10);
  border-radius: var(--radius-lg);
}
.portrait-viewer-head {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  font-size: 10px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase;
  color: var(--accent);
}
.portrait-viewer-media { display: block; max-width: 100%; max-height: 80vh; object-fit: contain; border-radius: var(--radius-xs); }

.sheet-scroll {
  flex: 1;
  overflow-y: auto; overflow-x: hidden;
}

/* The set header is a row: the toggle takes the width, the limit dots and the
   [+ ] sit at the end. The whole row is not the toggle any more — [+] is a
   different action, and a header you can only expand by hitting the words is a
   small target on a touch screen. */
.set-header {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 8px 0 4px;
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-dim);
}
.set-toggle {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  padding: 4px 0;
  background: none;
  border: none;
  cursor: pointer;
  user-select: none;
  font: inherit;
  text-transform: inherit;
  letter-spacing: inherit;
  color: inherit;
  text-align: left;
  transition: color 0.15s;
}
.set-toggle:hover {
  color: var(--text);
}
/* The drill-in's set row: the whole header is the tap target, because the list is
   navigation rather than a set of sections to expand. The accordion's row is not
   clickable itself — its `.set-toggle` button is — so this lives on the modifier,
   not on `.set-header`. */
.set-header-link {
  padding: 4px 0;
  cursor: pointer;
  user-select: none;
  transition: color 0.15s;
}
.set-header-link:hover {
  color: var(--text);
}
.set-chevron {
  flex-shrink: 0;
  width: 1em;
  opacity: 0.7;
}
.set-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* [+] and the dots both hug the right edge; the toggle's flex:1 pushes them. */
/* The glyph is centred by flex, not left to the text baseline: a bare button
   puts `＋` on its baseline in the inline flow, which lands it low and right of
   the box rather than in the middle of it. `padding: 0` for the same reason —
   the UA's default padding shifts the glyph off-centre. */
.set-add {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  padding: 0;
  line-height: 1;
  border-radius: var(--radius-xs);
  border: 1px solid var(--overlay-10);
  background: var(--overlay-4);
  color: var(--text-dim);
  font-size: 14px;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}
.set-add:hover {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-12);
}
.set-traits {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-left: 2px;
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
  .set-back { align-self: flex-start;
    margin-bottom: 6px; }
  /* Previous hugs the left edge, Next the right. `align-self: stretch` is what
     makes the row span the list — right-aligned, the two buttons could only ever
     huddle together. The auto margin (not justify-content) keeps a *lone* Next on
     the right, the way the single button always sat, while a lone Previous sits
     left. */
  .set-nav { align-self: stretch;
    margin-top: 6px;
    display: flex;
    flex-wrap: wrap;
    gap: 6px; }
  .set-nav-next { margin-left: auto; }

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
  border-radius: var(--radius-sm);
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
.picker-filter {
  width: 100%;
  margin-bottom: 6px;
  padding: 6px 10px;
  font-size: 13px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--overlay-10);
  background: var(--overlay-4);
  color: var(--text);
}
.picker-type {
  font-size: 11px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.5px;
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
.name-primary { font-size: 20px; font-weight: 700; font-family: var(--font-display); }
.name-secondary { display: flex; align-items: center; min-height: 17px; }
/* These overrides must beat the primitive's .btn-md/.btn-link rules from the
   child stylesheet, hence the .header-title descendant prefix. */
.header-title .name-primary-btn {
  padding: 0;
  font-size: 20px;
  font-weight: 700;
  font-family: var(--font-display);
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
  border-radius: var(--radius-xs);
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
  border-radius: var(--radius-pill);
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
  border-radius: var(--radius);
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
  border-radius: var(--radius-sm);
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

/* Faction roster (B108) — a member list, not a trait list, so it gets its own
   row shape: the name leads, the role is the payload, the type badge stays
   quiet. Reuses `.empty` for the two empty states. */
.roster-title {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 2px;
  color: var(--text-dim);
  margin-bottom: 6px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--overlay-6);
}
.roster-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.roster-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 6px 8px;
  background: var(--overlay-4);
  border: 1px solid var(--overlay-6);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.roster-row:hover { border-color: var(--accent); }
.roster-row:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.roster-name {
  flex: 1 1 auto;
  font-size: 13px;
  color: var(--text);
}
.roster-type {
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 1px;
  color: var(--text-dim);
  border: 1px solid var(--overlay-10);
  border-radius: var(--radius-xs);
  padding: 1px 4px;
}
.roster-role {
  font-size: 12px;
  font-style: italic;
  color: var(--text-dim);
}
.roster-role.unset { opacity: 0.5; }
.roster-rank {
  font-size: 11px;
  color: var(--accent);
}

/* Incoming ties (B134) — one group per holder, so the question "who is tied to
   this place" is answered by the group heads and the *what* hangs underneath. */
.ties-title {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 2px;
  color: var(--text-dim);
  margin-bottom: 6px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--overlay-6);
}
.ties-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.tie-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.tie-holder {
  display: flex;
  align-items: baseline;
  gap: 8px;
  cursor: pointer;
  border-radius: var(--radius-xs);
  transition: color 0.15s;
}
.tie-holder:hover .tie-name { color: var(--accent); }
.tie-holder:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.tie-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.tie-desc {
  font-size: 12px;
  font-style: italic;
  color: var(--text-dim);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* The tie's own traits sit under their holder — indented by the same amount a
   sub-trait list is, since they are a step further from the sheet's subject. */
.tie-traits {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-left: 12px;
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

.sfx-card {
  display: flex;
  flex-direction: column;
  gap: 1px;
  align-self: flex-start;
  max-width: 100%;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
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

/* Rules the current place lends the entity (see Place-Owned Rules). Quiet by
   design: it belongs to the room, not to you, so it sits under your own cards
   and names where it comes from. */
.place-sfx-rules {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
  padding-top: 6px;
  border-top: 1px dashed var(--overlay-8);
}
.place-sfx-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.place-sfx-label {
  font-size: 10px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-dim);
}

/* Rules that live on the GM, on the roaming GM's play surface. The same quiet
   treatment as a place's rules, for the same reason: they are not on anyone in
   the scene below them. */
.gm-sfx-rules {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px dashed var(--overlay-8);
}
.gm-sfx-label {
  font-size: 10px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-dim);
}

/* The troupe rows are the widest thing the sheet ever holds, and the sheet's
   narrowest home is the phone-landscape dock — 179px of column, the same width
   the tab row above is written against. There the name, which is the one thing
   the row is *for*, ellipsised to nothing while the state pill kept its space.
   Wrapping instead of truncating lets the pill fall onto its own line, so the
   row degrades at any width rather than at one. Scoped to the sheet's play
   surface: the GM panel is never this narrow and keeps its single-line row. */
@media (max-height: 500px) {
  .sheet-embedded :deep(.play-overview .main-line),
  .sheet-embedded :deep(.play-overview .recency-line),
  .sheet-embedded :deep(.play-overview .scene-line),
  .sheet-embedded :deep(.play-overview .scene-counts) { flex-wrap: wrap; row-gap: 2px; }
  /* `flex: 0 0 auto` keeps the scene counts on one line however little room there
     is — a flex container only wraps inside a width it has been *given*, and that
     basis gives it none. Given one, the two counts stack instead of the second
     being cut mid-word. */
  .sheet-embedded :deep(.play-overview .scene-counts) { flex: 1 1 auto; min-width: 0; }
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
  border-radius: var(--radius-xs);
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
  border-radius: var(--radius-sm);
  padding: 6px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.4);
}
.rel-editor input {
  width: 180px;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-xs);
  background: var(--bg-input);
  color: var(--text);
  font-size: 12px;
  font-style: italic;
  outline: none;
}
.rel-editor input:focus {
  border-color: var(--accent);
}
.sheet-pills { display: flex; gap: 0; margin-bottom: 10px; border-radius: var(--radius-chip); overflow: hidden; border: 1px solid var(--overlay-8); }/* The tabs are a *row*, and the group is drawn as one rounded control. Below
   roughly 200px — which the phone-landscape dock reaches, at 179px of sheet —
   the tab buttons used to wrap onto a second line *inside* that rounded border,
   so the group stopped reading as a group. One scrollable row instead: the tabs
   keep their size, the group keeps its shape, and the overflow is reachable by
   swiping. The `↩` settings button is a sibling of this wrapper, so it stays
   pinned to the right rather than scrolling away with the tabs. */
.sheet-pills > div {
  display: flex;
  flex: 1;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: none;
}
.sheet-pills > div::-webkit-scrollbar { display: none; }
.pill { padding: 5px 14px; font-size: 11px; border: none; cursor: pointer; background: var(--overlay-2); color: var(--text-dim); transition: background 0.15s, color 0.15s; }
.pill + .pill { border-left: 1px solid var(--overlay-6); }
.pill:hover { background: var(--overlay-4); color: var(--text); }
.pill.active { background: var(--accent-dim); color: var(--text); font-weight: 600; }
/* ── Trait detail (read-only) ────────────────────────
   A drill-in that replaces the trait list. Layout priority top-down: the
   mechanical cores (rating, SFX) above the narrative tail. */

/* Descendant-prefixed so these beat the primitive's .btn-md/.btn-link rules. */



/* The rating band is the play target, mirroring the trait row's rating zone. */


/* Rendered only when it has rows, so a plain static trait ends at Notes. */


/* The derived natural-language rules line inside a detail SFX card. Brighter
   than the flavour lead-in above it — this is the text that tells you what the
   SFX actually does. */
</style>
