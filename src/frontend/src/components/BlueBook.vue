<template>
  <div v-if="visible && !embedded" class="bluebook-backdrop" @click.self="$emit('close')">
    <div class="bluebook-panel">
      <div class="bb-header">
        <h2>{{ entityName }}'s Blue Book</h2>
        <button class="bb-close" @click="$emit('close')" title="Close">✕</button>
      </div>
    </div>
  </div>
  <div v-if="visible && embedded">
      <span class="bb-header-label">📘 {{ entityName }}</span>

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
              <img v-if="e.sheetPortrait" :src="e.sheetPortrait" class="bb-suggestion-img" />
              <span v-else class="bb-suggestion-avatar">{{ e.name.charAt(0) }}</span>
              {{ e.name }}
            </button>
          </div>
        </div>
        <input v-model="composeTitle" class="bb-input" placeholder="Title (optional)" @keyup.enter="focusBody" />
        <div class="bb-tags-row">
          <input v-model="composeTags" class="bb-input" placeholder="Tags: dreams, investigation (comma-separated)" @focus="tagFocused = true" @blur="tagBlur" @input="onTagInput" />
          <div v-if="tagFocused && filteredTagSuggestions.length" class="bb-suggestions">
            <button v-for="t in filteredTagSuggestions" :key="t" class="bb-suggestion-item" @mousedown.prevent @click="addTag(t)">{{ t }}</button>
          </div>
        </div>
        <div class="bb-body-row-full">
          <textarea ref="bodyEl" v-model="composeBody" class="bb-textarea" :placeholder="composePlaceholder" rows="4" @keyup.enter.ctrl="send"></textarea>
        </div>
        <div class="bb-compose-actions">
          <button class="bb-send" @click="send" :disabled="!composeBody.trim() || sending">{{ sending ? '…' : sendLabel }}</button>
          <button class="bb-cancel" @click="cancelCompose()">Cancel</button>
        </div>
      </div>

      <!-- ── Entries ── -->
      <div class="bb-entries">
        <div v-if="loading" class="bb-empty">Loading…</div>
        <div v-else-if="!filteredEntries.length" class="bb-empty">No entries yet.</div>
        <div v-if="allEntryTags.length" class="bb-tag-filter">
          <button :class="{ active: !selectedTag }" @click="selectedTag = null">All</button>
          <button v-for="t in allEntryTags" :key="t" :class="{ active: selectedTag === t }" @click="selectedTag = (selectedTag === t ? null : t)">#{{ t }}</button>
        </div>
        <div v-for="m in filteredEntries" :key="m.id" class="bb-entry">
          <div class="bb-entry-header">
            <div v-if="m.senderEntityId !== m.recipientEntityId" class="bb-sender-row">
              <img v-if="senderPortrait(m.senderEntityId)" :src="senderPortrait(m.senderEntityId)" class="bb-sender-img" />
              <span v-else class="bb-sender-avatar">{{ senderInitial(m.senderEntityId) }}</span>
              <span class="bb-sender-name">{{ senderName(m.senderEntityId) }}</span>
              <span v-if="m.relationshipDescription" class="bb-rel">· {{ m.relationshipDescription }} ·</span>
            </div>
            <div v-else class="bb-journal-badge">📓 Journal entry</div>
            <div v-if="m.title" class="bb-entry-title">{{ m.title }}</div>
          </div>
          <div v-if="m.tags?.length" class="bb-entry-tags"><span v-for="t in m.tags" :key="t" class="bb-tag">#{{ t }}</span></div>
          <div class="bb-body">{{ m.body }}</div>
          <div class="bb-entry-actions">
            <button v-if="m.senderEntityId !== m.recipientEntityId" class="bb-reply-btn" @click="replyTo(m)">↩ Reply</button>
          </div>
        </div>
      </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, computed } from 'vue'
import { useApi } from '../composables/useApi.js'

const props = defineProps({
  entityId: { type: String, required: true },
  entityName: { type: String, default: '' },
  visible: { type: Boolean, default: false },
  embedded: { type: Boolean, default: false },
})

defineEmits(['close'])

const { graphql } = useApi()

const loading = ref(false)
const sending = ref(false)
const entries = ref([])

const showCompose = ref(false)
const showRecipientList = ref(false)
const composeMode = ref('new')
const composeTitle = ref('')
const composeBody = ref('')
const composeTags = ref('')
const composeRecipientId = ref('')
const composeRecipientName = ref('')
const bodyEl = ref(null)

const tagFocused = ref(false)
const allTags = ref([])
const relatedEntities = ref([])

const senderNames = ref({})
const senderPortraits = ref({})
const replyTarget = ref(null)
const replyName = ref('')

const selectedTag = ref(null)

const QUERY_FEED = `
  query($eid: ID!) {
    incoming: incomingMessages(entityId: $eid) { id senderEntityId recipientEntityId body title createdAt relationshipDescription tags kind }
    journal: journal(entityId: $eid) { id senderEntityId recipientEntityId body title createdAt tags kind }
  }
`

const SEND_LETTER = `mutation($sender:ID!,$recipient:ID!,$body:String!,$tags:[String!]){sendMessage(input:{senderEntityId:$sender,recipientEntityId:$recipient,kind:LETTER,body:$body,tags:$tags}){id}}`
const ADD_JOURNAL = `mutation($eid:ID!,$title:String!,$body:String!,$tags:[String!]){addJournalEntry(input:{entityId:$eid,title:$title,body:$body,tags:$tags}){id}}`
const MESSAGE_TAGS = `query{messageTags}`
const RELATED_ENTITIES = `query($eid:ID!,$q:String!){relatedEntities(entityId:$eid,query:$q){id name sheetPortrait}}`

const composePlaceholder = computed(() => {
  if (composeMode.value === 'reply') return 'Write your reply…'
  return isSelfRecipient.value ? 'Write a journal entry…' : 'Write a letter…'
})

const isSelfRecipient = computed(() => {
  const id = composeMode.value === 'reply' ? replyTarget.value : composeRecipientId.value
  return id === props.entityId
})

const sendLabel = computed(() => {
  if (composeMode.value === 'reply') return 'Reply'
  if (isSelfRecipient.value) return 'Create journal entry'
  return 'Send ' + (composeRecipientName.value || composeRecipientId.value)
})

const allEntryTags = computed(() => {
  const seen = new Set()
  for (const m of entries.value) for (const t of (m.tags || [])) seen.add(t)
  return [...seen].sort()
})

const filteredEntries = computed(() => {
  if (!selectedTag.value) return entries.value
  return entries.value.filter(m => (m.tags || []).includes(selectedTag.value))
})

const filteredTagSuggestions = computed(() => {
  if (!composeTags.value) return allTags.value
  const parts = composeTags.value.split(',')
  const current = parts[parts.length - 1].trim().toLowerCase()
  if (!current) return []
  return allTags.value.filter(t => t.toLowerCase().includes(current) && !parts.slice(0, -1).map(p => p.trim()).includes(t))
})

async function fetch() {
  if (!props.visible) return
  loading.value = true
  try {
    const data = await graphql(QUERY_FEED, { eid: props.entityId })
    const inc = data?.incoming || []
    const jrn = data?.journal || []
    const seen = new Set()
    entries.value = [...inc, ...jrn].filter(m => seen.has(m.id) ? false : (seen.add(m.id), true)).sort((a, b) => (b.createdAt || '').localeCompare(a.createdAt || ''))
    for (const m of inc) {
      if (!senderNames.value[m.senderEntityId]) fetchEntityInfo(m.senderEntityId)
    }
  } finally { loading.value = false }
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

function senderName(eid) { return senderNames.value[eid] || eid }
function senderPortrait(eid) { return senderPortraits.value[eid] || null }
function senderInitial(eid) { const n = senderName(eid); return n ? n.charAt(0).toUpperCase() : '?' }

function parseTags() { return composeTags.value.split(',').map(t => t.trim()).filter(Boolean) }

async function send() {
  await nextTick()
  if (!composeBody.value.trim() || sending.value) return
  sending.value = true
  try {
    const body = composeBody.value.trim()
    const tags = parseTags()
    if (isSelfRecipient.value) {
      await graphql(ADD_JOURNAL, { eid: props.entityId, title: composeTitle.value.trim(), body, tags: tags.length ? tags : null })
    } else {
      const recipient = composeMode.value === 'reply' ? replyTarget.value : composeRecipientId.value
      if (!recipient) return
      await graphql(SEND_LETTER, { sender: props.entityId, recipient, body, tags: tags.length ? tags : null })
    }
  } finally {
    sending.value = false
    cancelCompose()
    await fetch()
  }
}

async function fetchRelatedEntities() {
  const data = await graphql(RELATED_ENTITIES, { eid: props.entityId, q: '' })
  relatedEntities.value = data?.relatedEntities || []
}

function toggleRecipientList() {
  showRecipientList.value = !showRecipientList.value
  if (showRecipientList.value && !relatedEntities.value.length) fetchRelatedEntities()
}

function selectSelf() {
  composeRecipientId.value = props.entityId
  composeRecipientName.value = props.entityName || 'Me'
  showRecipientList.value = false
}

function selectRecipient(entity) {
  composeRecipientName.value = entity.name
  composeRecipientId.value = entity.id
  showRecipientList.value = false
}

function onTagInput() {}
function addTag(tag) {
  const parts = composeTags.value.split(',').map(t => t.trim()).filter(Boolean)
  if (parts[parts.length - 1]) parts.pop()
  parts.push(tag)
  composeTags.value = parts.join(', ') + ', '
  tagFocused.value = true
  bodyEl.value?.focus()
}
function tagBlur() { setTimeout(() => { tagFocused.value = false }, 150) }

function openCompose(mode) {
  composeMode.value = mode || 'new'
  if (composeMode.value === 'new') {
    composeRecipientId.value = props.entityId
    composeRecipientName.value = props.entityName || 'Me'
  }
  showCompose.value = true
  nextTick(() => bodyEl.value?.focus())
}

function cancelCompose() {
  showCompose.value = false
  showRecipientList.value = false
  composeTitle.value = ''
  composeBody.value = ''
  composeTags.value = ''
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
.bb-recipient-row,.bb-tags-row{position:relative}
.bb-recipient-btn{display:flex;align-items:center;gap:4px;padding:4px 8px;border:1px solid var(--border);border-radius:4px;background:var(--bg-input);color:var(--text);font-size:12px;cursor:pointer;width:100%}
.bb-recipient-btn:hover{border-color:var(--accent)}
.bb-recipient-arrow{font-size:10px;color:var(--text-dim);margin-left:auto}
.bb-recipient-picker{position:relative}
.bb-suggestions{position:absolute;top:100%;left:0;right:0;z-index:10;background:var(--bg-panel);border:1px solid var(--border);border-radius:4px;max-height:160px;overflow-y:auto;box-shadow:0 4px 12px rgba(0,0,0,0.4)}
.bb-suggestion-item{display:flex;align-items:center;gap:6px;width:100%;text-align:left;padding:4px 8px;border:none;background:none;color:var(--text-dim);font-size:12px;cursor:pointer}
.bb-suggestion-item:hover{background:var(--bg-hover);color:var(--text)}
.bb-suggestion-img{width:20px;height:20px;border-radius:50%;object-fit:cover}
.bb-suggestion-avatar{width:20px;height:20px;border-radius:50%;background:var(--accent-dim);color:var(--accent);font-size:10px;font-weight:700;display:flex;align-items:center;justify-content:center}
.bb-compose-actions{display:flex;gap:6px;justify-content:flex-end}
.bb-send{padding:4px 12px;border:none;border-radius:4px;background:var(--accent);color:#fff;font-size:12px;cursor:pointer;white-space:nowrap}
.bb-send:disabled{opacity:0.4;cursor:default}
.bb-send:not(:disabled):hover{opacity:0.85}
.bb-cancel{padding:4px 12px;border:1px solid var(--border);border-radius:4px;background:transparent;color:var(--text-dim);font-size:12px;cursor:pointer}
.bb-cancel:hover{color:var(--text);background:var(--bg-hover)}
.bb-entries{flex:1;overflow-y:auto;padding:8px 12px}
.bb-empty{color:var(--text-dim);font-size:13px;text-align:center;padding:32px 0}
.bb-tag-filter{display:flex;gap:4px;flex-wrap:wrap;padding:4px 0 8px;border-bottom:1px solid var(--border);margin-bottom:8px}
.bb-tag-filter button{padding:2px 8px;border:1px solid var(--border);border-radius:12px;background:transparent;color:var(--text-dim);font-size:11px;cursor:pointer;transition:background 0.15s,color 0.15s,border-color 0.15s}
.bb-tag-filter button:hover{background:var(--bg-hover);color:var(--text)}
.bb-tag-filter button.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.bb-entry{padding:10px 0;border-bottom:1px solid var(--border)}
.bb-entry:last-child{border-bottom:none}
.bb-entry-header{display:flex;align-items:center;gap:4px;margin-bottom:4px;flex-wrap:wrap}
.bb-sender-row{display:flex;align-items:center;gap:4px}
.bb-sender-img{width:24px;height:24px;border-radius:50%;object-fit:cover;flex-shrink:0}
.bb-sender-avatar{width:24px;height:24px;border-radius:50%;background:var(--accent-dim);color:var(--accent);font-size:11px;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.bb-sender-name{font-weight:600;font-size:12px;color:var(--accent)}
.bb-journal-badge{font-size:11px;color:var(--text-dim)}
.bb-entry-title{font-size:13px;font-weight:600;color:var(--text);margin-bottom:2px}
.bb-entry-tags{display:flex;gap:4px;flex-wrap:wrap;margin:2px 0 4px}
.bb-tag{font-size:10px;color:var(--accent);opacity:0.7}
.bb-rel{font-size:11px;color:var(--text-dim);font-style:italic}
.bb-body{font-size:13px;color:var(--text);line-height:1.4;white-space:pre-wrap}
.bb-entry-actions{margin-top:4px}
.bb-reply-btn{background:none;border:none;color:var(--accent);font-size:11px;cursor:pointer;padding:2px 6px;border-radius:4px}
.bb-reply-btn:hover{background:var(--bg-hover)}
</style>
