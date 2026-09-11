<template>
  <div v-if="visible && !embedded" class="bluebook-backdrop" @click.self="$emit('close')">
    <div class="bluebook-panel">
      <div class="bb-header">
        <h2>{{ entityName }}'s Blue Book</h2>
        <button class="bb-close" @click="$emit('close')" title="Close">✕</button>
      </div>
    </div>
  </div>
  <div v-if="visible && embedded" class="bb-embedded">

      <!-- ── Compose toggle ── -->
      <div v-if="!showCompose" class="bb-compose-toggle">
        <button class="bb-write-btn" @click="openCompose()">📝 New entry</button>
      </div>

      <!-- ── Compose ── -->
      <div v-if="showCompose" class="bb-compose">
        <div v-if="composeMode === 'reply'" class="bb-reply-to">
          <span>Replying to <strong>{{ replyName }}</strong></span>
          <button class="bb-reply-cancel" @click="cancelCompose()">cancel</button>
        </div>
        <div v-if="composeMode !== 'reply'" class="bb-recipient-row">
          <button class="bb-recipient-btn" @click="toggleRecipientList">
            <span v-if="isSelfRecipient">📓 Self (journal)</span>
            <span v-else>✉ {{ composeRecipientName }}</span>
            <span class="bb-recipient-arrow">{{ showRecipientList ? '▴' : '▾' }}</span>
          </button>
          <div v-if="showRecipientList" class="bb-suggestions">
            <button class="bb-suggestion-item" :class="{ active: isSelfRecipient }" @mousedown.prevent @click="selectSelf">
              📓 Self (journal)
            </button>
            <button v-for="e in relatedEntities" :key="e.id" class="bb-suggestion-item" :class="{ active: composeRecipientId === e.id }" @mousedown.prevent @click="selectRecipient(e)">
              <MediaImage v-if="e.sheetPortrait" :src="e.sheetPortrait" class="bb-suggestion-img" alt="" />
              <span v-else class="bb-suggestion-avatar">{{ e.name.charAt(0) }}</span>
              {{ e.name }}
            </button>
          </div>
        </div>
        <input v-model="composeTitle" class="bb-input" placeholder="Title (optional)" @keyup.enter="focusBody" />
        <TagInput v-model="composeThreads" :suggestions="allThreads" placeholder="Threads — pick an existing one or type a new one" aria-label="Threads" />
        <div class="bb-body-row-full">
          <textarea ref="bodyEl" v-model="composeBody" class="bb-textarea" :placeholder="composePlaceholder" rows="4" @keyup.enter.ctrl="send"></textarea>
        </div>
        <div class="bb-images-row">
          <div v-for="(img, i) in composeImages" :key="i" class="bb-image-preview">
            <img :src="img" />
            <button class="bb-image-remove" @click="composeImages.splice(i, 1)" title="Remove image">✕</button>
          </div>
          <label class="bb-image-add" :class="{ uploading: uploadingImage }">
            <input type="file" ref="imageInput" accept="image/*" @change="uploadImage" hidden />
            {{ uploadingImage ? '…' : '📷' }}
          </label>
        </div>
        <div v-if="uploadError" class="bb-upload-error">{{ uploadError }}</div>
        <div class="bb-compose-actions">
          <button class="bb-send" @click="send" :disabled="!(composeBody.trim() || composeImages.length || composeTitle.trim()) || sending">{{ sending ? '…' : sendLabel }}</button>
          <button class="bb-cancel" @click="cancelCompose()">Cancel</button>
        </div>
      </div>

      <!-- ── Thread filter (sticky above entries) ── -->
      <div v-if="allEntryThreads.length && entries.length" class="bb-thread-filter">
        <button :class="{ active: !selectedThread }" @click="selectedThread = null">All</button>
        <button v-for="t in allEntryThreads" :key="t" :class="{ active: selectedThread === t }" @click="selectedThread = (selectedThread === t ? null : t)">#{{ t }}</button>
      </div>

      <!-- ── Entries ── -->
      <div ref="entriesEl" class="bb-entries">
        <div v-if="loading" class="bb-empty">Loading…</div>
        <div v-else-if="!displayEntries.length" class="bb-empty">No entries yet.</div>
        <TransitionGroup v-else name="bb-list" tag="div" class="bb-list" :class="{ 'bb-phasing': filterPhasing }">
          <div v-for="(g, gidx) in renderGroups" :key="g.key" :data-bb-idx="g.type === 'entry' ? g.idx : -1" :style="{ animation: 'bb-enter 0.3s ease both', animationDelay: (renderGroups.length - 1 - gidx) * 0.04 + 's' }" class="bb-entry" :class="{ 'bb-dragging': g.type === 'entry' && dragIndex === g.idx, 'bb-drag-over': g.type === 'entry' && dragOverIndex === g.idx, 'bb-continuation': g.type === 'entry' && entryContinuations.has(g.entry.id) }" :draggable="g.type === 'entry'" @dragstart="g.type === 'entry' && dragStart($event, g.idx)" @dragover="dragOver" @drop="drop" @dragend="dragEnd" @touchstart="g.type === 'entry' && touchStart($event, g.idx)">
            <!-- ── Chain group: consecutive transversal records, inline images ── -->
            <template v-if="g.type === 'chain'">
              <div class="bb-entry-header">
                <div class="bb-record-badge">{{ recordIcon(g.entries[0]) }} {{ recordLabel(g.entries[0]) }}</div>
              </div>
              <div class="bb-record-locations">
                <template v-for="(locId, li) in chainLocationIds(g.entries)" :key="locId">
                  <img v-if="locationPortraits[locId]" :src="locationPortraits[locId]" class="bb-location-img" alt="" @click="viewImage(locationPortraits[locId])" />
                  <span v-else class="bb-location-missing">{{ locationNames[locId] || locId }}</span>
                  <span v-if="li < chainLocationIds(g.entries).length - 1" class="bb-location-arrow">→</span>
                </template>
                <span v-if="!chainLocationIds(g.entries).length" class="bb-entry-title bb-record-title">{{ chainTitle(g.entries) }}</span>
              </div>
            </template>
            <!-- ── Single entry (message or non-transversal record) ── -->
            <template v-else>
              <div v-if="!entryContinuations.has(g.entry.id)" class="bb-entry-header">
                <div v-if="g.entry.recordType" class="bb-record-badge">{{ recordIcon(g.entry) }} {{ recordLabel(g.entry) }}</div>
                <div v-else-if="g.entry.senderEntityId !== g.entry.recipientEntityId" class="bb-sender-row">
                  <MediaImage v-if="senderPortrait(g.entry.senderEntityId)" :src="senderPortrait(g.entry.senderEntityId)" class="bb-sender-img" alt="" />
                  <span v-else class="bb-sender-avatar">{{ senderInitial(g.entry.senderEntityId) }}</span>
                  <span class="bb-sender-name">{{ senderName(g.entry.senderEntityId) }}</span>
                  <span v-if="g.entry.relationshipDescription" class="bb-rel">· {{ g.entry.relationshipDescription }} ·</span>
                </div>
                <div v-else class="bb-journal-badge">📓 Journal entry</div>
                <div v-if="g.entry.title && !g.entry.recordType" class="bb-entry-title">{{ g.entry.title }}</div>
              </div>
              <div v-if="g.entry.recordType && g.entry.title" class="bb-entry-title bb-record-title">{{ g.entry.title }}</div>
              <div v-if="g.entry.threads?.length && !g.entry.recordType" class="bb-entry-threads"><span v-for="t in g.entry.threads" :key="t" class="bb-thread">#{{ t }}</span></div>
              <div class="bb-body" v-html="renderMarkdown(g.entry.body)"></div>
              <div v-if="g.entry.images?.length" class="bb-images">
                <img v-for="(img, i) in g.entry.images" :key="i" :src="img" class="bb-image" @click="viewImage(img)" />
              </div>
              <div class="bb-entry-actions">
                <button v-if="g.entry.senderEntityId !== g.entry.recipientEntityId && lastInGroup.has(g.entry.id)" class="bb-reply-btn" @click="replyTo(g.entry)">↩ Reply</button>
              </div>
            </template>
          </div>
        </TransitionGroup>
      </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, computed } from 'vue'
import { useApi } from '../composables/useApi.js'
import MediaImage from './MediaImage.vue'
import TagInput from './ui/TagInput.vue'
import { useDragDrop } from '../composables/useDragDrop.js'
import { renderMarkdown } from '../utils/markdown.js'

const props = defineProps({
  entityId: { type: String, required: true },
  entityName: { type: String, default: '' },
  visible: { type: Boolean, default: false },
  embedded: { type: Boolean, default: false },
  viewerId: { type: String, default: '' },
})

defineEmits(['close'])

const selfId = computed(() => props.viewerId || props.entityId)

const { graphql } = useApi()

const loading = ref(false)
const sending = ref(false)
const entries = ref([])

const showCompose = ref(false)
const showRecipientList = ref(false)
const composeMode = ref('new')
const composeTitle = ref('')
const composeBody = ref('')
const composeThreads = ref([])
const composeImages = ref([])
const uploadingImage = ref(false)
const uploadError = ref('')
const imageInput = ref(null)
const entriesEl = ref(null)
const composeRecipientId = ref('')
const composeRecipientName = ref('')
const bodyEl = ref(null)

const allThreads = ref([])
const relatedEntities = ref([])

const senderNames = ref({})
const senderPortraits = ref({})
const locationPortraits = ref({})
const locationNames = ref({})
const replyTarget = ref(null)
const replyName = ref('')

const selectedThread = ref(null)

const QUERY_TIMELINE = `
  query($eid: ID!) {
    timeline(entityId: $eid) {
      id senderEntityId recipientEntityId body images title createdAt relationshipDescription threads kind afterIds
    }
  }
`

const QUERY_RECORDS = `
  query($eid: ID!) {
    historicalRecords(entityId: $eid) {
      id entityId recordType universe sessionId data createdAt
    }
  }
`

const UPDATE_MESSAGE = `mutation($id:ID!,$afterIds:[ID!]!){updateMessage(input:{id:$id,afterIds:$afterIds})}`

const SEND_LETTER = `mutation($sender:ID!,$recipient:ID!,$body:String!,$images:[String!]!,$afterIds:[ID!]!,$threads:[String!]!){sendMessage(input:{senderEntityId:$sender,recipientEntityId:$recipient,kind:LETTER,body:$body,images:$images,afterIds:$afterIds,threads:$threads}){id}}`
const ADD_JOURNAL = `mutation($eid:ID!,$title:String!,$body:String!,$images:[String!]!,$afterIds:[ID!]!,$threads:[String!]!){addJournalEntry(input:{entityId:$eid,title:$title,body:$body,images:$images,afterIds:$afterIds,threads:$threads}){id}}`
const MESSAGE_TAGS = `query{messageThreads}`
const RELATED_ENTITIES = `query($eid:ID!,$q:String!){relatedEntities(entityId:$eid,query:$q){id name sheetPortrait}}`

const RECORD_LABELS = { roll_table: 'Roll table', contest: 'Contest', transversal: 'Transversal' }
const RECORD_ICONS = { roll_table: '🎲', contest: '⚔️', transversal: '🧭' }

function recordLabel(m) { return RECORD_LABELS[m.recordType] || m.recordType }
function recordIcon(m) { return RECORD_ICONS[m.recordType] || '🎲' }

function formatRecord(rec) {
  const d = rec.data || {}
  if (rec.recordType === 'transversal') {
    const from = d.from_name || d.from_location || ''
    const to = d.to_name || d.to_location || ''
    if (from && to) return `${from} → ${to}`
    if (to) return `Arrived at ${to}`
    if (from) return `Departed ${from}`
    return 'Location changed'
  }
  const parts = [d.life_path_name, d.table_name, d.entry_label].filter(x => x != null && x !== '')
  return parts.length ? parts.join(' | ') : rec.recordType
}

function normalizeRecord(rec) {
  return {
    id: rec.id,
    recordType: rec.recordType,
    data: rec.data || {},
    senderEntityId: props.entityId,
    recipientEntityId: props.entityId,
    title: formatRecord(rec),
    body: '',
    images: [],
    threads: [rec.recordType],
    createdAt: rec.createdAt,
  }
}

function recordLocations(m) {
  if (m.recordType !== 'transversal') return []
  const d = m.data || {}
  const ids = []
  if (d.from_location) ids.push(d.from_location)
  if (d.to_location && d.to_location !== d.from_location) ids.push(d.to_location)
  return ids
}

function byCreatedAt(a, b) {
  if (!a.createdAt) return 1
  if (!b.createdAt) return -1
  return a.createdAt < b.createdAt ? -1 : a.createdAt > b.createdAt ? 1 : 0
}

const composePlaceholder = computed(() => {
  if (composeMode.value === 'reply') return 'Write your reply…'
  return isSelfRecipient.value ? 'Write a journal entry…' : 'Write a letter…'
})

const isSelfRecipient = computed(() => {
  const id = composeMode.value === 'reply' ? replyTarget.value : composeRecipientId.value
  return id === selfId.value
})

const sendLabel = computed(() => {
  if (composeMode.value === 'reply') return 'Reply'
  if (isSelfRecipient.value) return 'Create journal entry'
  return 'Send ' + (composeRecipientName.value || composeRecipientId.value)
})

const allEntryThreads = computed(() => {
  const seen = new Set()
  for (const m of entries.value) for (const t of (m.threads || [])) seen.add(t)
  return [...seen].sort()
})

const filteredEntries = computed(() => {
  if (!selectedThread.value) return entries.value
  return entries.value.filter(m => (m.threads || []).includes(selectedThread.value))
})

// Phased display for smooth filter transitions
const displayEntries = ref([])
const filterPhasing = ref(false)
let filterTimer = null

async function refreshEntries(newList) {
  displayEntries.value = []
  await nextTick()
  displayEntries.value = [...newList]
  // Scroll to bottom after cascade completes
  const delay = (newList.length - 1) * 40 + 300 + 50
  setTimeout(() => {
    const el = entriesEl.value
    if (el) el.scrollTop = el.scrollHeight
  }, delay)
}

watch(selectedThread, (newVal) => {
  clearTimeout(filterTimer)
  if (newVal) {
    filterPhasing.value = true
    filterTimer = setTimeout(async () => {
      await refreshEntries(filteredEntries.value)
      filterTimer = setTimeout(() => { filterPhasing.value = false }, 50)
    }, 200)
  } else {
    refreshEntries(entries.value)
  }
})

watch(entries, () => {
  clearTimeout(filterTimer)
  refreshEntries(filteredEntries.value)
  filterPhasing.value = false
}, { immediate: true })

const entryContinuations = computed(() => {
  const items = displayEntries.value
  const cont = new Set()
  for (let i = 1; i < items.length; i++) {
    const prev = items[i - 1]
    const curr = items[i]
    if (prev.recordType || curr.recordType) {
      // Consecutive records of the same type form one group
      if (prev.recordType && curr.recordType && prev.recordType === curr.recordType) {
        cont.add(curr.id)
      }
      continue
    }
    const sameSender = prev.senderEntityId === curr.senderEntityId
    const sharedThread = curr.threads?.length && curr.threads.some(t => prev.threads?.includes(t))
    if (sameSender || sharedThread) cont.add(curr.id)
  }
  return cont
})

const lastInGroup = computed(() => {
  const items = displayEntries.value
  const last = new Set()
  for (let i = 0; i < items.length; i++) {
    const next = items[i + 1]
    if (!next || !entryContinuations.value.has(next.id)) last.add(items[i].id)
  }
  return last
})

// Merge consecutive transversal records into single chain groups so their
// location images render inline (wrapping) as one connected path.
const renderGroups = computed(() => {
  const items = displayEntries.value
  const groups = []
  let i = 0
  while (i < items.length) {
    const m = items[i]
    if (m.recordType === 'transversal') {
      const chain = [m]
      let j = i + 1
      while (j < items.length && items[j].recordType === 'transversal') {
        chain.push(items[j])
        j++
      }
      groups.push({ key: 'chain-' + chain[0].id, type: 'chain', entries: chain })
      i = j
    } else {
      groups.push({ key: m.id, type: 'entry', entry: m, idx: i })
      i++
    }
  }
  return groups
})

function chainLocationIds(group) {
  const ids = []
  for (const m of group) {
    const d = m.data || {}
    if (d.from_location && ids[ids.length - 1] !== d.from_location) ids.push(d.from_location)
    if (d.to_location && ids[ids.length - 1] !== d.to_location) ids.push(d.to_location)
  }
  return ids
}

function chainTitle(group) {
  const names = []
  const fd = group[0]?.data || {}
  if (fd.from_name && names[names.length - 1] !== fd.from_name) names.push(fd.from_name)
  for (const m of group) {
    const d = m.data || {}
    if (d.to_name && names[names.length - 1] !== d.to_name) names.push(d.to_name)
  }
  return names.join(' → ')
}

async function fetch() {
  if (!props.visible) return
  loading.value = true
  try {
    const [timelineData, recordsData] = await Promise.all([
      graphql(QUERY_TIMELINE, { eid: props.entityId }),
      graphql(QUERY_RECORDS, { eid: props.entityId }),
    ])
    const messages = timelineData?.timeline || []
    const records = (recordsData?.historicalRecords || []).map(normalizeRecord)
    entries.value = [...messages, ...records].sort(byCreatedAt)
    for (const m of entries.value) {
      if (m.recordType) continue
      if (m.senderEntityId !== props.entityId && !senderNames.value[m.senderEntityId]) {
        fetchEntityInfo(m.senderEntityId)
      }
    }
    // Resolve sheet portraits for transversal record locations
    const seenLocs = new Set(Object.keys(locationPortraits.value))
    for (const m of entries.value) {
      for (const locId of recordLocations(m)) {
        if (!seenLocs.has(locId)) {
          seenLocs.add(locId)
          fetchLocationPortrait(locId)
        }
      }
    }
  } finally { loading.value = false }
  fetchThreads()
  nextTick(() => {
    const el = entriesEl.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function fetchEntityInfo(eid) {
  try {
    const data = await graphql(`{entity(id:"${eid}"){name sheetPortrait}}`)
    if (data?.entity) {
      senderNames.value[eid] = data.entity.name
      if (data.entity.sheetPortrait) senderPortraits.value[eid] = data.entity.sheetPortrait
    }
  } catch {}
}

async function fetchLocationPortrait(locId) {
  try {
    const data = await graphql(`{entity(id:"${locId}"){name sheetPortrait}}`)
    if (data?.entity) {
      locationNames.value[locId] = data.entity.name
      if (data.entity.sheetPortrait) {
        locationPortraits.value[locId] = data.entity.sheetPortrait
      }
    }
  } catch {}
}

async function fetchThreads() {
  try {
    const data = await graphql(MESSAGE_TAGS)
    if (data?.messageThreads) allThreads.value = data.messageThreads
  } catch {}
}

async function reorder(srcIdx, dropIdx) {
  if (srcIdx < 0 || srcIdx === dropIdx) return

  const visible = [...displayEntries.value]
  if (!visible.length) return

  // Reorder: remove from srcIdx, insert at dropIdx
  const [X] = visible.splice(srcIdx, 1)
  const targetIdx = srcIdx < dropIdx ? dropIdx - 1 : dropIdx
  visible.splice(targetIdx, 0, X)

  // Rebuild after_ids: each entry points to the one above it
  const updates = []
  for (let i = 0; i < visible.length; i++) {
    const newAfterIds = i > 0 ? [visible[i - 1].id] : []
    const current = (visible[i].afterIds || []).sort().join(',')
    const proposed = newAfterIds.sort().join(',')
    if (current !== proposed) {
      updates.push(graphql(UPDATE_MESSAGE, { id: visible[i].id, afterIds: newAfterIds }))
    }
  }

  if (updates.length) await Promise.all(updates)
  await fetch()
}

const { source: dragIndex, over: dragOverIndex, touchStart, dragStart, dragOver, drop, dragEnd } = useDragDrop({
  resolveTarget: (el) => {
    const row = el && el.closest ? el.closest('.bb-entry') : null
    if (!row || row.dataset.bbIdx === undefined) return null
    const idx = parseInt(row.dataset.bbIdx)
    return idx >= 0 ? idx : null
  },
  onCommit: ({ from, to }) => reorder(from, to),
})

function senderName(eid) { return senderNames.value[eid] || eid }
function senderPortrait(eid) { return senderPortraits.value[eid] || null }
function senderInitial(eid) { const n = senderName(eid); return n ? n.charAt(0).toUpperCase() : '?' }

async function send() {
  console.log("[BB] send() called", JSON.stringify({ body: composeBody.value, sending: sending.value, isSelf: isSelfRecipient.value, mode: composeMode.value, recipientId: composeRecipientId.value }))
  await nextTick()
  const hasContent = composeBody.value.trim() || composeImages.value.length || composeTitle.value.trim()
  if (!hasContent || sending.value) { console.log("[BB] send() blocked"); return }
  sending.value = true
  console.log("[BB] send() executing")
  try {
    const body = composeBody.value.trim()
    const images = [...composeImages.value]
    const tags = [...composeThreads.value]
    if (isSelfRecipient.value) {
      await graphql(ADD_JOURNAL, { eid: selfId.value, title: composeTitle.value.trim(), body, images, afterIds: [], threads: tags.length ? tags : [] })
    } else {
      const recipient = composeMode.value === 'reply' ? replyTarget.value : composeRecipientId.value
      if (!recipient) return
      await graphql(SEND_LETTER, { sender: selfId.value, recipient, body, images, afterIds: [], threads: tags.length ? tags : [] })
    }
  } finally {
    sending.value = false
    cancelCompose()
    await fetch()
  }
}

async function uploadImage(e) {
  const input = e.target
  const file = input.files?.[0]
  if (!file) return
  uploadingImage.value = true
  uploadError.value = ''
  try {
    const form = new FormData()
    form.append('file', file)
    // Use XHR to bypass PWA service worker (SW intercepts fetch but not XHR)
    const data = await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', '/api/v1/media/upload')
      xhr.onload = () => {
        let payload
        try { payload = JSON.parse(xhr.responseText) } catch { payload = null }
        if (xhr.status >= 200 && xhr.status < 300 && payload?.path) resolve(payload)
        else reject(new Error(payload?.detail || `Upload failed (${xhr.status})`))
      }
      xhr.onerror = () => reject(new Error('Network error'))
      xhr.send(form)
    })
    if (data.path) composeImages.value.push(data.path)
  } catch (err) {
    uploadError.value = err.message || 'Image upload failed'
    console.error('[BB] image upload failed', err.message)
  } finally {
    uploadingImage.value = false
    input.value = ''
  }
}
function viewImage(src) { window.open(src, '_blank') }

async function fetchRelatedEntities() {
  const data = await graphql(RELATED_ENTITIES, { eid: selfId.value, q: '' })
  relatedEntities.value = data?.relatedEntities || []
}

function toggleRecipientList() {
  showRecipientList.value = !showRecipientList.value
  if (showRecipientList.value && !relatedEntities.value.length) fetchRelatedEntities()
}

function selectSelf() {
  composeRecipientId.value = selfId.value
  composeRecipientName.value = props.entityName || 'Me'
  showRecipientList.value = false
}

function selectRecipient(entity) {
  composeRecipientName.value = entity.name
  composeRecipientId.value = entity.id
  showRecipientList.value = false
}

function openCompose(mode, recipient) {
  composeMode.value = mode || 'new'
  if (recipient) {
    composeRecipientId.value = recipient.id
    composeRecipientName.value = recipient.name
  } else if (composeMode.value === 'new') {
    composeRecipientId.value = selfId.value
    composeRecipientName.value = props.entityName || 'Me'
  }
  showCompose.value = true
  nextTick(() => bodyEl.value?.focus())
}

defineExpose({ openCompose, refresh: fetch })

function cancelCompose() {
  showCompose.value = false
  showRecipientList.value = false
  composeTitle.value = ''
  composeBody.value = ''
  composeThreads.value = []
  composeImages.value = []
  composeRecipientId.value = ''
  composeRecipientName.value = ''
  replyTarget.value = null
  replyName.value = ''
  composeMode.value = 'new'
}

function replyTo(msg) {
  replyTarget.value = msg.senderEntityId
  replyName.value = senderName(msg.senderEntityId)
  composeBody.value = ''
  openCompose('reply')
}

function focusBody() { bodyEl.value?.focus() }
function formatTime(iso) {
  if (!iso) return ''
  try { return new Date(iso).toLocaleDateString(undefined, { month:'short',day:'numeric',hour:'2-digit',minute:'2-digit' }) }
  catch { return iso }
}

watch(() => props.visible, (v) => { if (v) fetch() }, { immediate: true })
</script>

<style scoped>
.bluebook-backdrop{position:fixed;inset:0;z-index:100;background:rgba(0,0,0,0.6);display:flex;align-items:center;justify-content:center}
.bluebook-panel{background:var(--bg-panel);backdrop-filter:blur(16px);border-radius:var(--radius);border:1px solid var(--border);width:480px;max-width:95vw;max-height:85vh;display:flex;flex-direction:column;overflow:hidden}
.bb-header{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--border)}
.bb-header h2{font-size:16px;margin:0}
.bb-close{background:none;border:none;color:var(--text-dim);font-size:16px;cursor:pointer;padding:4px 8px;border-radius:4px}
.bb-close:hover{background:var(--bg-hover);color:var(--text)}
.bb-compose-toggle{padding:8px 12px;border-bottom:1px solid var(--border)}
.bb-write-btn{padding:6px 12px;border:1px dashed var(--border);border-radius:6px;background:transparent;color:var(--text-dim);font-size:13px;cursor:pointer;width:100%;text-align:left}
.bb-write-btn:hover{color:var(--text);border-color:var(--accent)}
.bb-compose{padding:10px 12px;border-bottom:1px solid var(--border);display:flex;flex-direction:column;gap:6px}
.bb-reply-to{display:flex;align-items:center;justify-content:space-between;font-size:11px;color:var(--text-dim)}
.bb-reply-cancel{background:none;border:none;color:var(--accent);font-size:11px;cursor:pointer}
.bb-recipient-display{display:flex;align-items:center;gap:6px}
.bb-self-indicator{font-size:11px;color:var(--accent)}
.bb-other-indicator{font-size:11px;color:var(--text-dim)}
.bb-change-recipient{background:none;border:none;color:var(--accent);font-size:11px;cursor:pointer;padding:1px 6px;border-radius:4px}
.bb-change-recipient:hover{background:var(--bg-hover)}
.bb-input{padding:6px 10px;border:1px solid var(--border);border-radius:4px;background:var(--bg-input);color:var(--text);font-size:12px;outline:none}
.bb-input:focus{border-color:var(--accent)}
.bb-body-row-full{display:flex;flex-direction:column}
.bb-body-row-full .bb-textarea{width:100%;min-height:80px}
.bb-textarea{flex:1;padding:6px 10px;border:1px solid var(--border);border-radius:4px;background:var(--bg-input);color:var(--text);font-size:12px;resize:none;outline:none;font-family:inherit}
.bb-textarea:focus{border-color:var(--accent)}
.bb-recipient-row{position:relative}
.bb-recipient-btn{display:flex;align-items:center;gap:4px;padding:4px 8px;border:1px solid var(--border);border-radius:4px;background:var(--bg-input);color:var(--text);font-size:12px;cursor:pointer;width:100%}
.bb-recipient-btn:hover{border-color:var(--accent)}
.bb-recipient-arrow{font-size:10px;color:var(--text-dim);margin-left:auto}
.bb-recipient-picker{position:relative}
.bb-suggestions{position:absolute;top:100%;left:0;right:0;z-index:10;background:var(--bg-panel);border:1px solid var(--border);border-radius:4px;max-height:160px;overflow-y:auto;box-shadow:0 4px 12px rgba(0,0,0,0.4)}
.bb-suggestion-item{display:flex;align-items:center;gap:6px;width:100%;text-align:left;padding:4px 8px;border:none;background:none;color:var(--text-dim);font-size:12px;cursor:pointer}
.bb-suggestion-item:hover{background:var(--bg-hover);color:var(--text)}
.bb-suggestion-img{width:20px;height:20px;border-radius:50%;object-fit:cover}
.bb-suggestion-avatar{width:20px;height:20px;border-radius:50%;background:var(--accent-dim);color:var(--accent);font-size:10px;font-weight:700;display:flex;align-items:center;justify-content:center}
.bb-embedded{display:flex;flex-direction:column;overflow:hidden;flex:1}
.bb-compose-actions{display:flex;gap:6px;justify-content:flex-end}
.bb-send{padding:4px 12px;border:none;border-radius:4px;background:var(--accent);color: var(--text-on-accent);font-size:12px;cursor:pointer;white-space:nowrap}
.bb-send:disabled{opacity:0.4;cursor:default}
.bb-send:not(:disabled):hover{opacity:0.85}
.bb-cancel{padding:4px 12px;border:1px solid var(--border);border-radius:4px;background:transparent;color:var(--text-dim);font-size:12px;cursor:pointer}
.bb-cancel:hover{color:var(--text);background:var(--bg-hover)}
.bb-entries{flex:1;overflow-y:auto;overflow-x:hidden;padding:8px 12px}
.bb-empty{color:var(--text-dim);font-size:13px;text-align:center;padding:32px 0}
.bb-thread-filter{display:flex;gap:4px;flex-wrap:wrap;padding:4px 0 8px;border-bottom:1px solid var(--border);margin-bottom:8px}
.bb-thread-filter button{padding:2px 8px;border:1px solid var(--border);border-radius:12px;background:transparent;color:var(--text-dim);font-size:11px;cursor:pointer;transition:background 0.15s,color 0.15s,border-color 0.15s}
.bb-thread-filter button:hover{background:var(--bg-hover);color:var(--text)}
.bb-thread-filter button.active{background:var(--accent);color: var(--text-on-accent);border-color:var(--accent)}
.bb-entry{padding:10px 0;border-bottom:1px solid var(--border)}
.bb-entry:last-child{border-bottom:none}
.bb-entry.bb-dragging{opacity:0.4}
.bb-entry.bb-drag-over{border-top:2px solid var(--accent)}
.bb-entry-header{display:flex;align-items:center;gap:4px;margin-bottom:4px;flex-wrap:wrap}
.bb-sender-row{display:flex;align-items:center;gap:4px}
.bb-sender-img{width:24px;height:24px;border-radius:50%;object-fit:cover;flex-shrink:0}
.bb-sender-avatar{width:24px;height:24px;border-radius:50%;background:var(--accent-dim);color:var(--accent);font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.bb-sender-name{font-weight:600;font-size:12px;color:var(--accent)}
.bb-journal-badge{font-size:11px;color:var(--text-dim)}
.bb-record-badge{font-size:11px;color:var(--accent);text-transform:uppercase;letter-spacing:0.5px}
.bb-entry-title{font-size:13px;font-weight:600;color:var(--text);margin-bottom:2px}
.bb-record-title{font-size:12px;font-weight:500;color:var(--text);margin:2px 0}
.bb-record-locations{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:4px 0}
.bb-location-img{width:56px;height:56px;border-radius:6px;object-fit:cover;border:1px solid var(--border);cursor:pointer}
.bb-location-arrow{font-size:14px;color:var(--text-dim)}
.bb-location-missing{font-size:11px;color:var(--text-dim);padding:4px 8px;border:1px dashed var(--border);border-radius:6px}
.bb-entry-threads{display:flex;gap:4px;flex-wrap:wrap;margin:2px 0 4px}
.bb-thread{font-size:10px;color:var(--accent);opacity:0.7}
.bb-rel{font-size:11px;color:var(--text-dim);font-style:italic}
.bb-body{font-size:13px;color:var(--text);line-height:1.4;word-wrap:break-word}
.bb-body p{margin:4px 0}
.bb-body h1,.bb-body h2,.bb-body h3,.bb-body h4,.bb-body h5,.bb-body h6{margin:8px 0 4px;line-height:1.3}
.bb-body h1{font-size:18px}.bb-body h2{font-size:16px}.bb-body h3{font-size:15px}.bb-body h4{font-size:14px}.bb-body h5{font-size:13px}.bb-body h6{font-size:12px;color:var(--text-dim)}
.bb-body ul,.bb-body ol{margin:4px 0;padding-left:20px}
.bb-body li{margin:2px 0}
.bb-body code{font-family:monospace;font-size:12px;background:var(--bg-input);padding:1px 4px;border-radius:3px}
.bb-body pre{background:var(--bg-input);border:1px solid var(--border);border-radius:4px;padding:8px;overflow-x:auto;margin:6px 0}
.bb-body pre code{background:none;padding:0;font-size:12px}
.bb-body blockquote{border-left:3px solid var(--accent);margin:6px 0;padding:2px 10px;color:var(--text-dim)}
.bb-body a{color:var(--accent);text-decoration:underline}
.bb-images{display:flex;gap:6px;flex-wrap:wrap;margin:4px 0}
.bb-image{max-width:100%;max-height:200px;border-radius:4px;cursor:pointer;border:1px solid var(--border)}
.bb-images-row{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.bb-image-preview{position:relative;width:48px;height:48px;border-radius:4px;overflow:hidden;border:1px solid var(--border)}
.bb-image-preview img{width:100%;height:100%;object-fit:cover}
.bb-image-remove{position:absolute;top:0;right:0;background:rgba(0,0,0,0.7);color: var(--text-on-accent);border:none;font-size:8px;width:14px;height:14px;display:flex;align-items:center;justify-content:center;cursor:pointer;border-radius:0 0 0 4px;line-height:1}
.bb-image-add{cursor:pointer;width:48px;height:48px;border:1px dashed var(--border);border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:18px;color:var(--text-dim);transition:color 0.15s,border-color 0.15s}
.bb-image-add:hover{color:var(--accent);border-color:var(--accent)}
.bb-image-add.uploading{opacity:0.5;pointer-events:none}
.bb-upload-error{font-size:11px;color:var(--danger-soft);margin-top:4px}
.bb-entry-actions{margin-top:4px}
.bb-reply-btn{background:none;border:none;color:var(--accent);font-size:11px;cursor:pointer;padding:2px 6px;border-radius:4px}
.bb-reply-btn:hover{background:var(--bg-hover)}
</style>
