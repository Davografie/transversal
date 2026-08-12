<template>
  <div class="lpe-root">
    <div v-if="!section || section === '_root'" class="lpe-row"><label>Name</label><input v-model="form.name" /></div>
    <div v-if="!section || section === '_root'" class="lpe-row"><label>Description</label><textarea v-model="form.description" rows="2" /></div>
    <div v-if="!section || section === '_root'" class="lpe-row"><label>Universe</label><select v-model="form.universe"><option v-for="u in universes" :key="u.id" :value="u.id.replace(/^universe-/, '')">{{ u.name }}</option></select></div>

    <!-- Qualification -->
    <div v-if="!section || section === 'qualification'" class="lpe-section">
      <h4>Qualification</h4>
      <div class="lpe-row">
        <label>Trait</label>
        <GmTraitPicker v-model="form.qualification.traitId" :universe="form.universe" />
      </div>
      <div class="lpe-row"><label>Difficulty</label><select v-model="form.qualification.difficulty"><option v-for="d in dieTypes" :key="d" :value="d">{{ d }}</option></select></div>
      <div class="lpe-row">
        <label>Must be at location</label>
        <div class="lpe-search-wrap">
          <input v-model="qualSearch.location" @focus="qualDropdown.location = true" @blur="closeQualDropdown('location')" @input="qualDropdown.location = true" :placeholder="qualSelected.locationName || 'Search location…'" />
          <div v-if="qualDropdown.location" class="lpe-dropdown">
            <div v-if="!qualOptions.location.length" class="lpe-dropdown-empty">No matches</div>
            <div v-for="opt in qualOptions.location" :key="opt.id" class="lpe-dropdown-item" @mousedown.prevent="selectQual('location', opt)">{{ opt.name }}</div>
          </div>
        </div>
      </div>
      <div class="lpe-row">
        <label>Draft path</label>
        <div class="lpe-search-wrap">
          <input v-model="qualSearch.draft" @focus="qualDropdown.draft = true" @blur="closeQualDropdown('draft')" @input="qualDropdown.draft = true" :placeholder="qualSelected.draftName || 'Search life path…'" />
          <div v-if="qualDropdown.draft" class="lpe-dropdown">
            <div v-if="!qualOptions.draft.length" class="lpe-dropdown-empty">No matches</div>
            <div v-for="opt in qualOptions.draft" :key="opt.id" class="lpe-dropdown-item" @mousedown.prevent="selectQual('draft', opt)">{{ opt.name }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Discovery -->
    <div v-if="!section || section === 'discovery'" class="lpe-section">
      <h4>Discovery</h4>
      <p class="lpe-hint">At least one condition met → path becomes visible to the character.</p>

      <div class="lpe-item-form">
        <h5>{{ addNew ? 'New discovery condition' : 'Edit discovery condition' }}</h5>
        <div class="lpe-row">
          <label>Condition type</label>
          <select v-model="discEntryType">
            <option value="">— select —</option>
            <option value="atLocation">📍 Location</option>
            <option value="knowsEntity">👤 Knows entity</option>
            <option value="possessesTrait">🎯 Has trait</option>
            <option value="hasTraitRating">⭐ Trait rating</option>
            <option value="hasRelationship">🔗 Relationship</option>
          </select>
        </div>
        <div v-if="discEntryType" class="lpe-row">
          <label>{{ discTypeLabel(discEntryType) }}</label>
          <div class="lpe-search-wrap">
            <input v-model="discEntrySearch" @focus="discEntryDropdown = true" @blur="closeDiscEntryDropdown()" @input="discEntryDropdown = true" :placeholder="discEntryName || 'Search…'" />
            <div v-if="discEntryDropdown" class="lpe-dropdown">
              <div v-if="!discEntryOptions.length" class="lpe-dropdown-empty">No matches</div>
              <div v-for="opt in discEntryOptions" :key="opt.id" class="lpe-dropdown-item" @mousedown.prevent="selectDiscEntry(opt)">{{ opt.name }}</div>
            </div>
          </div>
        </div>
        <div v-if="discEntryType === 'hasTraitRating'" class="lpe-row">
          <label>Minimum die</label>
          <select v-model="discEntryDie"><option v-for="d in dieTypes" :key="d" :value="d">{{ d }}</option></select>
        </div>
        <button v-if="!addNew && discEntryType" class="lpe-del lpe-item-del" @click="deleteDiscFlatItem(discEntryIndex)">Delete</button>
      </div>
    </div>

    <!-- Curriculum -->
    <div v-if="!section || section === 'curriculum'" class="lpe-section">
      <h4>Curriculum</h4>
      <div v-if="itemIndex === null && !addNew">
        <div v-for="(c, i) in form.curriculum" :key="i" class="lpe-table-row">
          <GmTraitPicker v-model="c.traitId" :universe="form.universe" />
          <select v-model="c.createAt"><option v-for="d in dieTypes" :key="d" :value="d">{{ d }}</option></select>
          <label class="lpe-chk"><input type="checkbox" v-model="c.stepUp" /> StepUp</label>
          <button class="lpe-del" @click="form.curriculum.splice(i,1)">✕</button>
        </div>
        <button class="lpe-add" @click="form.curriculum.push({traitId:'',createAt:'d4',stepUp:false})">+ Add</button>
      </div>
      <div v-else-if="effectiveItemIndex !== null && form.curriculum[effectiveItemIndex]" class="lpe-item-form">
        <h5>{{ addNew ? 'New curriculum item' : `Curriculum item #${effectiveItemIndex + 1}` }}</h5>
        <div class="lpe-row">
          <label>Trait</label>
          <GmTraitPicker v-model="form.curriculum[effectiveItemIndex].traitId" :universe="form.universe" />
        </div>
        <div class="lpe-row"><label>Create at</label><select v-model="form.curriculum[effectiveItemIndex].createAt"><option v-for="d in dieTypes" :key="d" :value="d">{{ d }}</option></select></div>
        <label class="lpe-chk" style="display:flex;align-items:center;gap:6px;padding:4px 0;font-size:11px;color:var(--text);cursor:pointer"><input type="checkbox" v-model="form.curriculum[effectiveItemIndex].stepUp" /> Step up existing</label>
        <button class="lpe-del lpe-item-del" @click="deleteCurrentItem()">Delete</button>
      </div>
    </div>

    <!-- Survival -->
    <div v-if="!section || section === 'survival'" class="lpe-section">
      <h4>Survival</h4>
      <div class="lpe-row">
        <label>Traits</label>
        <div class="lpe-chips" v-if="form.survival.traitItems.length">
          <span v-for="item in form.survival.traitItems" :key="item.id" class="lpe-chip">
            {{ item.name }}
            <button class="lpe-chip-remove" @click="removeTraitChip('survival', item.id)">×</button>
          </span>
        </div>
        <div class="lpe-search-wrap">
          <input v-model="stSearch" @focus="stDropdown = true" @blur="stDropdown = false" @input="stDropdown = true" placeholder="Search traits…" />
          <div v-if="stDropdown" class="lpe-dropdown">
            <div v-if="!stOptions.length" class="lpe-dropdown-empty">No matches</div>
            <div v-for="opt in stOptions" :key="opt.id" class="lpe-dropdown-item" @mousedown.prevent="addTraitChip('survival', opt)">{{ opt.name }}</div>
          </div>
        </div>
      </div>
      <div class="lpe-row"><label>Difficulty</label><select v-model="form.survival.difficulty"><option v-for="d in dieTypes" :key="d" :value="d">{{ d }}</option></select></div>
      <div class="lpe-row"><label>Term penalty after</label><input v-model.number="form.survival.termPenaltyAfter" type="number" min="0" /></div>
    </div>

    <!-- Mishaps -->
    <div v-if="!section || section === 'mishap'" class="lpe-section">
      <h4>Mishaps</h4>
      <div v-if="itemIndex === null && !addNew">
        <div v-for="(m, i) in form.survival.mishaps" :key="i" class="lpe-table-row">
          <input v-model="m.description" placeholder="description" size="30" />
          <GmTraitPicker v-model="m.effectTraitId" :universe="form.universe" />
          <select v-model="m.effectDie"><option v-for="d in dieTypes" :key="d" :value="d">{{ d }}</option></select>
          <label class="lpe-chk"><input type="checkbox" v-model="m.must_muster_out" /> Muster</label>
          <button class="lpe-del" @click="form.survival.mishaps.splice(i,1)">✕</button>
        </div>
        <button class="lpe-add" @click="form.survival.mishaps.push({description:'',effectTraitId:'',effectDie:'d4',must_muster_out:false})">+ Mishap</button>
      </div>
      <div v-else-if="effectiveItemIndex !== null && form.survival.mishaps[effectiveItemIndex]" class="lpe-item-form">
        <h5>{{ addNew ? 'New mishap' : `Mishap #${effectiveItemIndex + 1}` }}</h5>
        <div class="lpe-row"><label>Description</label><textarea v-model="form.survival.mishaps[effectiveItemIndex].description" rows="2" placeholder="What happens" /></div>
        <div class="lpe-row">
          <label>Complication trait</label>
          <GmTraitPicker v-model="form.survival.mishaps[effectiveItemIndex].effectTraitId" :universe="form.universe" />
        </div>
        <div class="lpe-row"><label>Die type</label><select v-model="form.survival.mishaps[effectiveItemIndex].effectDie"><option v-for="d in dieTypes" :key="d" :value="d">{{ d }}</option></select></div>
        <label class="lpe-chk" style="display:flex;align-items:center;gap:6px;padding:4px 0;font-size:11px;color:var(--text);cursor:pointer"><input type="checkbox" v-model="form.survival.mishaps[effectiveItemIndex].must_muster_out" /> Forces muster out</label>
        <button class="lpe-del lpe-item-del" @click="deleteCurrentItem()">Delete</button>
      </div>
    </div>

    <!-- Events -->
    <div v-if="!section || section === 'events'" class="lpe-section">
      <h4>Events</h4>
      <div v-if="itemIndex === null && !addNew">
        <div v-for="(e, i) in form.events" :key="i" class="lpe-table-row">
          <input v-model="e.description" placeholder="description" size="30" />
          <GmTraitPicker v-model="e.effectTraitId" :universe="form.universe" />
          <select v-model="e.effectDie"><option v-for="d in dieTypes" :key="d" :value="d">{{ d }}</option></select>
          <button class="lpe-del" @click="form.events.splice(i,1)">✕</button>
        </div>
        <button class="lpe-add" @click="form.events.push({description:'',effectTraitId:'',effectDie:'d4'})">+ Event</button>
      </div>
      <div v-else-if="effectiveItemIndex !== null && form.events[effectiveItemIndex]" class="lpe-item-form">
        <h5>{{ addNew ? 'New event' : `Event #${effectiveItemIndex + 1}` }}</h5>
        <div class="lpe-row"><label>Description</label><textarea v-model="form.events[effectiveItemIndex].description" rows="2" placeholder="What happens" /></div>
        <div class="lpe-row">
          <label>Grants trait</label>
          <GmTraitPicker v-model="form.events[effectiveItemIndex].effectTraitId" :universe="form.universe" />
        </div>
        <div class="lpe-row"><label>Die type</label><select v-model="form.events[effectiveItemIndex].effectDie"><option v-for="d in dieTypes" :key="d" :value="d">{{ d }}</option></select></div>
        <button class="lpe-del lpe-item-del" @click="deleteCurrentItem()">Delete</button>
      </div>
    </div>

    <!-- Advancement -->
    <div v-if="!section || section === 'advancement'" class="lpe-section">
      <h4>Advancement</h4>
      <div class="lpe-row">
        <label>Traits</label>
        <div class="lpe-chips" v-if="form.advancement.traitItems.length">
          <span v-for="item in form.advancement.traitItems" :key="item.id" class="lpe-chip">
            {{ item.name }}
            <button class="lpe-chip-remove" @click="removeTraitChip('advancement', item.id)">×</button>
          </span>
        </div>
        <div class="lpe-search-wrap">
          <input v-model="atSearch" @focus="atDropdown = true" @blur="atDropdown = false" @input="atDropdown = true" placeholder="Search traits…" />
          <div v-if="atDropdown" class="lpe-dropdown">
            <div v-if="!atOptions.length" class="lpe-dropdown-empty">No matches</div>
            <div v-for="opt in atOptions" :key="opt.id" class="lpe-dropdown-item" @mousedown.prevent="addTraitChip('advancement', opt)">{{ opt.name }}</div>
          </div>
        </div>
      </div>
      <div class="lpe-row"><label>Difficulty</label><select v-model="form.advancement.difficulty"><option v-for="d in dieTypes" :key="d" :value="d">{{ d }}</option></select></div>
      <div v-if="itemIndex === null && !addNew">
        <h5>Ranks</h5>
        <div v-for="(r, i) in form.advancement.ranks" :key="i" class="lpe-table-row">
          <input v-model.number="r.number" type="number" min="1" size="3" placeholder="#" />
          <input v-model="r.name" placeholder="rank name" size="12" />
          <input v-model="r.benefitsStr" placeholder="benefits (JSON)" size="20" />
          <button class="lpe-del" @click="form.advancement.ranks.splice(i,1)">✕</button>
        </div>
        <button class="lpe-add" @click="form.advancement.ranks.push({number:(form.advancement.ranks.length+1),name:'',benefitsStr:'[]'})">+ Rank</button>
      </div>
      <div v-else-if="effectiveItemIndex !== null && form.advancement.ranks[effectiveItemIndex]" class="lpe-item-form">
        <h5>{{ addNew ? 'New rank' : `Rank #${effectiveItemIndex + 1}` }}</h5>
        <div class="lpe-row"><label>Number</label><input v-model.number="form.advancement.ranks[effectiveItemIndex].number" type="number" min="1" /></div>
        <div class="lpe-row"><label>Name</label><input v-model="form.advancement.ranks[effectiveItemIndex].name" placeholder="rank name" /></div>
        <div class="lpe-row"><label>Benefits</label><input v-model="form.advancement.ranks[effectiveItemIndex].benefitsStr" placeholder="JSON, e.g. [{type:'razmerit',amount:100}]" /></div>
        <button class="lpe-del lpe-item-del" @click="deleteCurrentItem()">Delete</button>
      </div>
    </div>

    <!-- Muster Out -->
    <div v-if="!section || section === 'muster'" class="lpe-section">
      <h4>Muster Out</h4>
      <div class="lpe-row"><label>Per-term benefits</label><input v-model="form.musterOut.perTermBenefitsStr" placeholder="JSON, e.g. [{type:'razmerit',amount:'1d6'}]" /></div>
      <div class="lpe-row"><label>At-ranks</label><input v-model="form.musterOut.atRanksStr" placeholder="JSON, e.g. {1: [{type:'razmerit',amount:100}]}" /></div>
    </div>

    <div class="lpe-actions">
      <button class="lpe-save" @click="save" :disabled="saving">{{ saving ? 'Saving…' : 'Save' }}</button>
      <span v-if="saveMsg" class="lpe-msg">{{ saveMsg }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useApi } from '@/composables/useApi.js'
import { useTraitsConfig } from '@/composables/useTraitsConfig.js'
import GmTraitPicker from './GmTraitPicker.vue'
import GmLifePathDetailPanel from './GmLifePathDetailPanel.vue'

const { traitNameMap } = useTraitsConfig()

const props = defineProps({
  lp: { type: Object, required: true },
  section: { type: String, default: null },
  itemIndex: { type: Number, default: null },
  addNew: { type: Boolean, default: false },
  open: { type: Function, default: null },
  close: { type: Function, default: null },
})
const emit = defineEmits(['close'])
const { graphql } = useApi()
const dieTypes = ['d4','d6','d8','d10','d12']
const universes = ref([])
const saving = ref(false)

// ── Discovery autocomplete state ──────────────────────
const discSearch = reactive({
  atLocation: '',
  knowsEntity: '',
  possessesTrait: '',
  hasTraitRating: '',
  hasRelationship: '',
})
const discDropdown = reactive({
  atLocation: false,
  knowsEntity: false,
  possessesTrait: false,
  hasTraitRating: false,
  hasRelationship: false,
})
const locationNameMap = ref({})  // id → name for LOCATION entities
const entityNameMap = ref({})    // id → name for all entities
const lifePathNameMap = ref({})  // id → name for life paths

// ── Qualification autocomplete state ─────────────────
const qualSearch = reactive({ trait: '', location: '', draft: '' })
const qualDropdown = reactive({ trait: false, location: false, draft: false })
const qualSelected = reactive({ traitName: '', locationName: '', draftName: '' })

const qualOptions = computed(() => ({
  trait: filterSingleOpts(traitNameMap.value, qualSearch.trait, form.qualification.traitId),
  location: filterSingleOpts(locationNameMap.value, qualSearch.location, form.qualification.mustBeAtLocation),
  draft: filterSingleOpts(lifePathNameMap.value, qualSearch.draft, form.qualification.draft),
}))

function filterSingleOpts(nameMap, search, excludeId) {
  const s = search.toLowerCase()
  return Object.entries(nameMap)
    .filter(([id, name]) => (!s || name.toLowerCase().includes(s)) && id !== excludeId)
    .map(([id, name]) => ({ id, name }))
    .slice(0, 20)
}

function selectQual(field, opt) {
  form.qualification[field === 'trait' ? 'traitId' : field === 'location' ? 'mustBeAtLocation' : 'draft'] = opt.id
  qualSelected[field + 'Name'] = opt.name
  qualSearch[field] = ''
  qualDropdown[field] = false
}

function closeQualDropdown(field) {
  setTimeout(() => { qualDropdown[field] = false }, 150)
}

// ── Single-item trait autocomplete state ─────────────
const itemSearch = reactive({ curriculum: '', mishap: '', event: '' })
const itemDropdown = reactive({ curriculum: false, mishap: false, event: false })
const itemSelected = reactive({ curriculumName: '', mishapName: '', eventName: '' })

function itemOpts(field) {
  const excludeId = form[field === 'mishap' ? 'survival' : field].mishaps
    ? form.survival.mishaps[effectiveItemIndex.value]?.effectTraitId
    : field === 'event'
    ? form.events[effectiveItemIndex.value]?.effectTraitId
    : form.curriculum[effectiveItemIndex.value]?.traitId
  const s = itemSearch[field].toLowerCase()
  return Object.entries(traitNameMap.value)
    .filter(([id, name]) => (!s || name.toLowerCase().includes(s)) && id !== excludeId)
    .map(([id, name]) => ({ id, name }))
    .slice(0, 20)
}

function selectItemTrait(field, opt) {
  if (field === 'curriculum') {
    form.curriculum[effectiveItemIndex.value].traitId = opt.id
  } else if (field === 'mishap') {
    form.survival.mishaps[effectiveItemIndex.value].effectTraitId = opt.id
  } else {
    form.events[effectiveItemIndex.value].effectTraitId = opt.id
  }
  itemSelected[field + 'Name'] = opt.name
  itemSearch[field] = ''
  itemDropdown[field] = false
}

function closeItemDropdown(field) {
  setTimeout(() => { itemDropdown[field] = false }, 150)
}

// ── Survival / Advancement trait chip state ──────────
const stSearch = ref('')
const stDropdown = ref(false)
const atSearch = ref('')
const atDropdown = ref(false)

const stOptions = computed(() => chipTraitOpts(form.survival.traitItems, stSearch.value))
const atOptions = computed(() => chipTraitOpts(form.advancement.traitItems, atSearch.value))

function chipTraitOpts(items, search) {
  const ids = new Set(items.map(i => i.id))
  const s = search.toLowerCase()
  return Object.entries(traitNameMap.value)
    .filter(([id, name]) => !ids.has(id) && (!s || name.toLowerCase().includes(s)))
    .map(([id, name]) => ({ id, name }))
    .slice(0, 20)
}

function addTraitChip(field, opt) {
  form[field].traitItems.push({ id: opt.id, name: opt.name })
  if (field === 'survival') { stSearch.value = ''; stDropdown.value = false }
  else { atSearch.value = ''; atDropdown.value = false }
}

function removeTraitChip(field, id) {
  const items = form[field].traitItems
  const idx = items.findIndex(i => i.id === id)
  if (idx >= 0) items.splice(idx, 1)
}

const discOptions = computed(() => {
  const fields = ['atLocation', 'knowsEntity', 'possessesTrait', 'hasTraitRating', 'hasRelationship']
  const result = {}
  for (const f of fields) {
    const map = f === 'atLocation' ? locationNameMap.value : f === 'possessesTrait' || f === 'hasTraitRating' ? traitNameMap.value : entityNameMap.value
    const items = f === 'hasTraitRating' ? form.discovery.hasTraitRatingItems : form.discovery[f + 'Items']
    const ids = new Set(items.map(i => i.id))
    const s = discSearch[f].toLowerCase()
    result[f] = Object.entries(map)
      .filter(([id, name]) => !ids.has(id) && (!s || name.toLowerCase().includes(s)))
      .map(([id, name]) => ({ id, name }))
      .slice(0, 20)
  }
  return result
})

function discItemName(field, item) {
  if (item.name && item.name !== item.id) return item.name
  const map = field === 'atLocation' ? locationNameMap.value : field === 'possessesTrait' || field === 'hasTraitRating' ? traitNameMap.value : entityNameMap.value
  return map[item.id] || item.id.replace(/^trait-/, '').replace(/[-_]\w{4}$/, '').replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function openDiscDropdown(field) {
  discDropdown[field] = true
}

function closeDiscDropdown(field) {
  setTimeout(() => { discDropdown[field] = false }, 150)
}

function addDiscItem(field, opt) {
  if (field === 'hasTraitRating') {
    form.discovery.hasTraitRatingItems.push({ id: opt.id, name: opt.name, die: 'd4' })
  } else {
    form.discovery[field + 'Items'].push({ id: opt.id, name: opt.name })
  }
  discSearch[field] = ''
  discDropdown[field] = false
}

function removeDiscItem(field, id) {
  const items = field === 'hasTraitRating' ? form.discovery.hasTraitRatingItems : form.discovery[field + 'Items']
  const idx = items.findIndex(i => i.id === id)
  if (idx >= 0) items.splice(idx, 1)
}

// ── Discovery single-entry form state ─────────────────
const discEntryType = ref('')
const discEntryValue = ref('')
const discEntryIndex = ref(null)
const discEntryDie = ref('d4')
const discEntryName = ref('')
const discEntrySearch = ref('')
const discEntryDropdown = ref(false)

const discEntryOptions = computed(() => {
  const map = discEntryType.value === 'atLocation' ? locationNameMap.value
    : (discEntryType.value === 'possessesTrait' || discEntryType.value === 'hasTraitRating') ? traitNameMap.value
    : entityNameMap.value
  const s = discEntrySearch.value.toLowerCase()
  return Object.entries(map)
    .filter(([id, name]) => (!s || name.toLowerCase().includes(s)) && id !== discEntryValue.value)
    .map(([id, name]) => ({ id, name }))
    .slice(0, 20)
})

function discTypeLabel(type) {
  const labels = { atLocation: '📍 Location', knowsEntity: '👤 Knows entity', possessesTrait: '🎯 Has trait', hasTraitRating: '⭐ Trait rating', hasRelationship: '🔗 Relationship' }
  return labels[type] || type
}

function selectDiscEntry(opt) {
  console.log('[disc-entry] selectDiscEntry', { type: discEntryType.value, opt, die: discEntryDie.value, wasEditing: discEntryIndex.value !== null })
  // Remove old entry if editing existing
  if (discEntryIndex.value !== null) {
    deleteDiscFlatItem(discEntryIndex.value)
  }
  discEntryValue.value = opt.id
  discEntryName.value = opt.name
  discEntrySearch.value = ''
  discEntryDropdown.value = false
  // Persist to form discovery arrays
  if (discEntryType.value === 'hasTraitRating') {
    form.discovery.hasTraitRatingItems.push({ id: opt.id, name: opt.name, die: discEntryDie.value })
  } else {
    form.discovery[discEntryType.value + 'Items'].push({ id: opt.id, name: opt.name })
  }
  discEntryIndex.value = discFlatItems.value.findIndex(i => i.value === opt.id && i.type === discEntryType.value)
}

function closeDiscEntryDropdown() {
  setTimeout(() => { discEntryDropdown.value = false }, 150)
}


onMounted(async () => {
  try {
    const data = await graphql('{ entities(type: UNIVERSE) { id name } }')
    universes.value = data?.entities || []
  } catch {}
  // Fetch entity name maps for discovery autocomplete
  const universe = props.lp?.universe || ''
  try {
    const locData = await graphql(`{ entities(type: LOCATION, universe: "${universe}") { id name } }`)
    if (locData?.entities) {
      locData.entities.forEach(e => { locationNameMap.value[e.id] = e.name })
    }
  } catch {}
  try {
    const entData = await graphql(`{ entities(universe: "${universe}") { id name } }`)
    if (entData?.entities) {
      entData.entities.forEach(e => { entityNameMap.value[e.id] = e.name })
    }
  } catch {}
  try {
    const lpData = await graphql(`{ lifePaths(universe: "${universe}") { id name } }`)
    if (lpData?.lifePaths) {
      lpData.lifePaths.forEach(lp => { lifePathNameMap.value[lp.id] = lp.name })
    }
  } catch {}
  // Resolve qualification autocomplete names
  if (form.qualification.traitId) {
    qualSelected.traitName = traitNameMap.value[form.qualification.traitId] || ''
  }
  if (form.qualification.mustBeAtLocation) {
    qualSelected.locationName = locationNameMap.value[form.qualification.mustBeAtLocation] || ''
  }
  if (form.qualification.draft) {
    qualSelected.draftName = lifePathNameMap.value[form.qualification.draft] || ''
  }
  // Resolve pre-existing entity names on discovery items
  const allMap = { ...locationNameMap.value, ...entityNameMap.value }
  for (const item of form.discovery.atLocationItems) {
    if (item.name === item.id && allMap[item.id]) item.name = allMap[item.id]
  }
  for (const item of form.discovery.knowsEntityItems) {
    if (item.name === item.id && allMap[item.id]) item.name = allMap[item.id]
  }
  for (const item of form.discovery.hasRelationshipItems) {
    if (item.name === item.id && allMap[item.id]) item.name = allMap[item.id]
  }
})
const saveMsg = ref('')

function initForm() {
  const lp = props.lp
  console.log('[disc-init] initForm lp.discovery:', JSON.parse(JSON.stringify(lp.discovery || null)))
  const f = reactive({
    name: lp.name || '',
    description: lp.description || '',
    // type removed
    universe: lp.universe || '',
    qualification: {
      traitId: lp.qualification?.traitId || '',
      difficulty: lp.qualification?.difficulty || 'd4',
      mustBeAtLocation: lp.qualification?.mustBeAtLocation || '',
      draft: lp.qualification?.draft || '',
    },
    discovery: {
      atLocationItems: (lp.discovery?.atLocation || []).map(id => ({ id, name: id })),
      knowsEntityItems: (lp.discovery?.knowsEntity || []).map(id => ({ id, name: id })),
      possessesTraitItems: (lp.discovery?.possessesTrait || []).map(id => ({ id, name: traitNameMap.value[id] || id })),
      hasTraitRatingItems: Object.entries(lp.discovery?.hasTraitRating || {}).map(([id, die]) => ({ id, name: traitNameMap.value[id] || id, die: String(die).toLowerCase() })),
      hasRelationshipItems: (lp.discovery?.hasRelationship || []).map(id => ({ id, name: id })),
    },
    curriculum: (lp.curriculum || []).map(c => ({
      traitId: c.traitId || '',
      createAt: c.createAt || 'd4',
      stepUp: !!c.stepUp,
    })),
    survival: {
      traitItems: (lp.survival?.traitIds || []).map(id => ({ id, name: traitNameMap.value[id] || id })),
      difficulty: lp.survival?.difficulty || 'd6',
      termPenaltyAfter: lp.survival?.termPenaltyAfter || null,
      mishaps: (lp.survival?.mishaps || []).map(m => ({
        description: m.description || m,
        effectTraitId: m.effect?.trait_id || '',
        effectDie: String(m.effect?.die_type || 'd4').toLowerCase(),
        must_muster_out: !!m.must_muster_out,
      })),
    },
    events: (lp.events || []).map(e => ({
      description: e.description || '',
      effectTraitId: e.effect?.trait_id || '',
      effectDie: String(e.effect?.die_type || 'd4').toLowerCase(),
    })),
    advancement: {
      traitItems: (lp.advancement?.traitIds || []).map(id => ({ id, name: traitNameMap.value[id] || id })),
      difficulty: lp.advancement?.difficulty || 'd6',
      ranks: (lp.advancement?.ranks || []).map(r => ({
        number: r.number,
        name: r.name || '',
        benefitsStr: JSON.stringify(r.benefits || []),
      })),
    },
    musterOut: {
      perTermBenefitsStr: JSON.stringify(lp.musterOut?.perTermBenefits || []),
      atRanksStr: JSON.stringify(lp.musterOut?.atRanks || {}),
    },
  })
  return f
}
const form = initForm()
watch(() => props.lp, () => Object.assign(form, initForm()), { deep: false })

// ── Discovery flat items & single-entry form (after form init) ──
const discFlatItems = computed(() => {
  const items = []
  for (const item of form.discovery.atLocationItems)
    items.push({ type: 'atLocation', value: item.id, name: item.name })
  for (const item of form.discovery.knowsEntityItems)
    items.push({ type: 'knowsEntity', value: item.id, name: item.name })
  for (const item of form.discovery.possessesTraitItems)
    items.push({ type: 'possessesTrait', value: item.id, name: item.name })
  for (const item of form.discovery.hasTraitRatingItems)
    items.push({ type: 'hasTraitRating', value: item.id, die: item.die, name: item.name })
  for (const item of form.discovery.hasRelationshipItems)
    items.push({ type: 'hasRelationship', value: item.id, name: item.name })
  return items
})

function deleteDiscFlatItem(idx) {
  console.log('[disc-delete] deleteDiscFlatItem', { idx, discEntryIndex: discEntryIndex.value })
  const item = discFlatItems.value[idx]
  if (!item) { console.log('[disc-delete] no item at index', idx); return }
  if (item.type === 'hasTraitRating') {
    const i = form.discovery.hasTraitRatingItems.findIndex(x => x.id === item.value)
    if (i >= 0) form.discovery.hasTraitRatingItems.splice(i, 1)
  } else {
    const arr = form.discovery[item.type + 'Items']
    const i = arr.findIndex(x => x.id === item.value)
    if (i >= 0) arr.splice(i, 1)
  }
  // Clear the form so the user sees the deletion
  discEntryIndex.value = null
  discEntryType.value = ''
  discEntryValue.value = ''
  discEntryDie.value = 'd4'
  discEntryName.value = ''
}

watch(() => [props.section, props.itemIndex, props.addNew], ([s, idx, addNew]) => {
  if (s !== 'discovery') return
  console.log('[disc-init] watch fired', { s, idx, addNew, flatLen: discFlatItems.value.length })
  discEntrySearch.value = ''
  discEntryDropdown.value = false
  if (addNew) {
    discEntryIndex.value = null
    discEntryType.value = ''
    discEntryValue.value = ''
    discEntryDie.value = 'd4'
    discEntryName.value = ''
  } else if (idx !== null) {
    const item = discFlatItems.value[idx]
    console.log('[disc-init] editing item', idx, item)
    if (item) {
      discEntryIndex.value = idx
      discEntryType.value = item.type
      discEntryValue.value = item.value
      discEntryDie.value = item.die || 'd4'
      discEntryName.value = item.name || ''
    }
  }
}, { immediate: true })

// Push an empty item when +Add is used, so the single-item form has something to bind to
const addNewItemIndex = ref(null)
watch(() => [props.section, props.addNew], ([section, addNew]) => {
  if (!addNew || !section) return
  const emptyItem = getEmptyItem(section)
  const items = getSectionItems(form, section)
  if (items) {
    items.push(emptyItem)
    addNewItemIndex.value = items.length - 1
  }
}, { immediate: true })
const effectiveItemIndex = computed(() => {
  if (props.addNew) return addNewItemIndex.value
  return props.itemIndex
})

function getSectionItems(f, s) {
  switch (s) {
    case 'curriculum': return f.curriculum
    case 'mishap': return f.survival.mishaps
    case 'events': return f.events
    case 'advancement': return f.advancement.ranks
    default: return null
  }
}

function deleteCurrentItem() {
  if (effectiveItemIndex.value === null || !props.section) return
  const items = getSectionItems(form, props.section)
  if (items && effectiveItemIndex.value < items.length) {
    items.splice(effectiveItemIndex.value, 1)
  }
}

function getEmptyItem(section) {
  switch (section) {
    case 'mishap': return { description: '', effectTraitId: '', effectDie: 'd4', must_muster_out: false }
    case 'advancement': return { number: 0, name: '', benefitsStr: '[]' }
    default: return {}
  }
}

async function save() {
  saving.value = true
  saveMsg.value = ''
  const _d = (v) => String(v || '').toLowerCase()
  try {
    const survMishaps = form.survival.mishaps
      .filter(m => m.description || m.effectTraitId)
      .map(m => ({
        description: m.description,
        must_muster_out: m.must_muster_out,
        effect: m.effectTraitId ? { type: 'complication', trait_id: m.effectTraitId, die_type: _d(m.effectDie) } : {},
      }))
    const evts = form.events
      .filter(e => e.description || e.effectTraitId)
      .map(e => ({
        description: e.description,
        effect: e.effectTraitId ? { type: 'create_trait', trait_id: e.effectTraitId, die_type: _d(e.effectDie) } : {},
      }))
    let advRanks = []; let musterPerTerm = []; let musterAtRanks = {}
    try { advRanks = form.advancement.ranks
      .filter(r => r.name)
      .map(r => ({ number: r.number, name: r.name, benefits: JSON.parse(r.benefitsStr || '[]') })) } catch {}
    try { musterPerTerm = JSON.parse(form.musterOut.perTermBenefitsStr || '[]') } catch {}
    try { musterAtRanks = JSON.parse(form.musterOut.atRanksStr || '{}') } catch {}

    const vars = {
      id: props.lp.id,
      name: form.name,
      description: form.description,
      universe: form.universe,
      qualification: form.qualification.traitId ? {
        traitId: form.qualification.traitId,
        difficulty: _d(form.qualification.difficulty),
        mustBeAtLocation: form.qualification.mustBeAtLocation || null,
        draft: form.qualification.draft || null,
      } : null,
      discovery: {
        atLocation: form.discovery.atLocationItems.map(i => i.id),
        knowsEntity: form.discovery.knowsEntityItems.map(i => i.id),
        possessesTrait: form.discovery.possessesTraitItems.map(i => i.id),
        hasTraitRating: Object.fromEntries(form.discovery.hasTraitRatingItems.map(i => [i.id, _d(i.die)])),
        hasRelationship: form.discovery.hasRelationshipItems.map(i => i.id),
      },
      curriculum: form.curriculum.filter(c => c.traitId).map(c => ({
        traitId: c.traitId,
        createAt: _d(c.createAt),
        stepUp: c.stepUp,
      })),
      survival: {
        traitIds: form.survival.traitItems.map(i => i.id),
        difficulty: _d(form.survival.difficulty),
        termPenaltyAfter: form.survival.termPenaltyAfter ?? null,
        mishaps: survMishaps,
      },
      events: evts,
      advancement: {
        traitIds: form.advancement.traitItems.map(i => i.id),
        difficulty: _d(form.advancement.difficulty),
        ranks: advRanks,
      },
      musterOut: {
        perTermBenefits: musterPerTerm,
        atRanks: musterAtRanks,
      },
    }
    console.log('[disc-save] discovery payload:', JSON.stringify(vars.discovery))
    console.log('[disc-save] form state:', {
      atLocation: JSON.parse(JSON.stringify(form.discovery.atLocationItems)),
      knowsEntity: JSON.parse(JSON.stringify(form.discovery.knowsEntityItems)),
      possessesTrait: JSON.parse(JSON.stringify(form.discovery.possessesTraitItems)),
      hasTraitRating: JSON.parse(JSON.stringify(form.discovery.hasTraitRatingItems)),
      hasRelationship: JSON.parse(JSON.stringify(form.discovery.hasRelationshipItems)),
    })
    const result = await graphql(`mutation($id:String!,$name:String!,$description:String!,$universe:String!,$qualification:JSON,$discovery:JSON,$curriculum:JSON,$survival:JSON,$events:JSON,$advancement:JSON,$musterOut:JSON){saveLifePath(id:$id,name:$name,description:$description,universe:$universe,qualification:$qualification,discovery:$discovery,curriculum:$curriculum,survival:$survival,events:$events,advancement:$advancement,musterOut:$musterOut)}`, vars)
    saveMsg.value = 'Saved.'
    const realId = result?.saveLifePath?.id || vars.id
    console.log('[save] result:', result, 'realId:', realId, 'vars.id:', vars.id)
    window.dispatchEvent(new CustomEvent('lifepath-saved', { detail: { id: realId, universe: vars.universe, isNew: !vars.id } }))
    if (!vars.id) emit('close')
  } catch (e) {
    saveMsg.value = 'Error: ' + e.message
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.lpe-root { padding: 0; max-width: 480px; }
.lpe-row { margin-bottom: 6px; }
.lpe-row label { display: block; font-size: 10px; color: var(--text-dim); margin-bottom: 2px; }
.lpe-row input, .lpe-row select, .lpe-row textarea {
  width: 100%; font-size: 11px; padding: 4px 6px; border-radius: 3px; box-sizing: border-box;
  border: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.04); color: var(--text);
}
.lpe-section { margin-top: 10px; padding: 8px; border: 1px solid rgba(255,255,255,0.06); border-radius: 4px; }
.lpe-section h4 { font-size: 10px; color: var(--text-dim); text-transform: uppercase; margin: 0 0 6px 0; }
.lpe-section h5 { font-size: 9px; color: var(--text-dim); text-transform: uppercase; margin: 8px 0 4px; }
.lpe-table-row { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin-bottom: 6px; padding: 4px; border: 1px solid rgba(255,255,255,0.04); border-radius: 3px; }
.lpe-table-row input, .lpe-table-row select { font-size: 10px; padding: 2px 4px; border-radius: 3px; border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.03); color: var(--text); min-width: 0; }
.lpe-table-row input { flex: 1 1 120px; }
.lpe-chk { font-size: 9px; color: var(--text-dim); display: flex; align-items: center; gap: 2px; white-space: nowrap; }
.lpe-add { font-size: 9px; padding: 2px 8px; cursor: pointer; background: rgba(255,255,255,0.04); color: var(--text-dim); border: 1px solid rgba(255,255,255,0.06); border-radius: 3px; }
.lpe-add:hover { background: rgba(255,255,255,0.08); color: var(--text); }
.lpe-del { font-size: 10px; padding: 1px 5px; cursor: pointer; background: none; color: var(--text-dim); border: none; }
.lpe-del:hover { color: #e06060; }
.lpe-item-del { font-size: 11px; padding: 4px 10px; margin-top: 8px; border: 1px solid rgba(224,96,96,0.3); border-radius: 3px; color: #e06060; }
.lpe-item-del:hover { background: rgba(224,96,96,0.1); }
.lpe-actions { margin-top: 12px; display: flex; align-items: center; gap: 8px; }
.lpe-save { font-size: 12px; padding: 5px 18px; cursor: pointer; background: var(--accent-dim); color: var(--text); border: none; border-radius: 4px; }
.lpe-save:disabled { opacity: 0.5; cursor: default; }
.lpe-msg { font-size: 10px; color: var(--text-dim); }
.lpe-item-form { padding: 8px 0; }
.lpe-item-form h5 { font-size: 10px; color: var(--text-dim); text-transform: uppercase; margin: 0 0 8px 0; }

/* ── Discovery chips & autocomplete ─────────────── */
.lpe-chips { display: flex; flex-wrap: wrap; gap: 3px; margin-bottom: 4px; }
.lpe-chip {
  display: inline-flex; align-items: center; gap: 3px;
  font-size: 10px; padding: 1px 6px; border-radius: 3px;
  background: rgba(0,200,150,0.12); color: var(--accent);
  border: 1px solid rgba(0,200,150,0.2);
}
.lpe-chip-die { gap: 4px; }
.lpe-chip-die-sel {
  font-size: 9px; padding: 0 2px; border-radius: 2px;
  border: 1px solid rgba(0,200,150,0.3); background: rgba(0,200,150,0.08);
  color: var(--accent); cursor: pointer;
}
.lpe-chip-remove {
  font-size: 11px; line-height: 1; padding: 0 2px; cursor: pointer;
  background: none; border: none; color: var(--text-dim);
}
.lpe-chip-remove:hover { color: #e06060; }
.lpe-search-wrap { position: relative; }
.lpe-search-wrap input {
  width: 100%; font-size: 11px; padding: 4px 6px; border-radius: 3px; box-sizing: border-box;
  border: 1px solid rgba(255,255,255,0.1); background: rgba(255,255,255,0.04); color: var(--text);
}
.lpe-dropdown {
  position: absolute; top: 100%; left: 0; right: 0; z-index: 10;
  max-height: 140px; overflow-y: auto;
  background: #1a1a2e; border: 1px solid rgba(255,255,255,0.1); border-radius: 3px;
}
.lpe-dropdown-item {
  font-size: 10px; padding: 4px 8px; cursor: pointer; color: var(--text);
}
.lpe-dropdown-item:hover { background: rgba(0,200,150,0.1); color: var(--accent); }
.lpe-dropdown-empty { font-size: 10px; padding: 6px 8px; color: var(--text-dim); }
.lpe-hint { font-size: 9px; color: var(--text-dim); margin: 0 0 6px 0; }
</style>
