<template>
  <div v-if="visible" class="bluebook-backdrop" @click.self="$emit('close')">
    <div class="bluebook-panel">
      <div class="bb-header">
        <h2>{{ entityName }}'s Blue Book</h2>
        <button class="bb-close" @click="$emit('close')" title="Close">✕</button>
      </div>

      <div class="bb-tabs">
        <button :class="{ active: tab === 'inbox' }" @click="tab = 'inbox'">✉ Inbox</button>
        <button :class="{ active: tab === 'journal' }" @click="tab = 'journal'">📓 Journal</button>
      </div>

      <!-- ── Compose toggle ── -->
      <div v-if="!showCompose" class="bb-compose-toggle">
        <button class="bb-write-btn" @click="openCompose()">
          {{ tab === 'journal' ? '📝 New journal entry' : '📝 Write a letter' }}
        </button>
      </div>

      <!-- ── Compose ── -->
      <div v-if="showCompose" class="bb-compose">
        <div v-if="composeMode === 'reply'" class="bb-reply-to">
          <span>Replying to <strong>{{ replyName }}</strong></span>
          <button class="bb-reply-cancel" @click="cancelCompose()">cancel</button>
        </div>
        <input
          v-if="tab === 'journal'"
          v-model="composeTitle"
          class="bb-input"
          placeholder="Title (optional)"
          @keyup.enter="focusBody"
        />
        <div class="bb-body-row">
          <textarea
            ref="bodyEl"
            v-model="composeBody"
            class="bb-textarea"
            :placeholder="composePlaceholder"
            rows="2"
            @keyup.enter.ctrl="send"
          ></textarea>
          <button class="bb-send" @click="send" :disabled="!composeBody.trim() || sending" :title="composeMode === 'reply' ? 'Reply' : 'Send'">
            {{ sending ? '…' : 'Send' }}
          </button>
        </div>
        <input
          v-if="tab === 'journal'"
          v-model="composeTags"
          class="bb-input bb-tags"
          placeholder="Tags: dreams, investigation (comma-separated)"
        />
      </div>

      <!-- ── Inbox ── -->
      <div v-if="tab === 'inbox'" class="bb-entries">
        <div v-if="loading" class="bb-empty">Loading…</div>
        <div v-else-if="!inbox.length" class="bb-empty">No messages yet.</div>
        <div v-for="m in inbox" :key="m.id" class="bb-entry">
          <div class="bb-entry-header">
            <span class="bb-sender">{{ senderName(m.senderEntityId) }}</span>
            <span v-if="m.relationshipDescription" class="bb-rel">· {{ m.relationshipDescription }} ·</span>
          </div>
          <div class="bb-body">{{ m.body }}</div>
          <div class="bb-meta">
            <span class="bb-time">{{ formatTime(m.createdAt) }}</span>
            <span v-if="m.tags?.length" class="bb-tags">
              <span v-for="t in m.tags" :key="t" class="bb-tag">#{{ t }}</span>
            </span>
          </div>
          <div class="bb-entry-actions">
            <button class="bb-reply-btn" @click="replyTo(m)">↩ Reply</button>
          </div>
        </div>
      </div>

      <!-- ── Journal ── -->
      <div v-if="tab === 'journal'" class="bb-entries">
        <div v-if="loading" class="bb-empty">Loading…</div>
        <div v-else-if="!journal.length" class="bb-empty">No journal entries yet. Write your first.</div>
        <div v-for="m in journal" :key="m.id" class="bb-entry">
          <div v-if="m.title" class="bb-entry-title">{{ m.title }}</div>
          <div class="bb-body">{{ m.body }}</div>
          <div class="bb-meta">
            <span class="bb-time">{{ formatTime(m.createdAt) }}</span>
            <span v-if="m.tags?.length" class="bb-tags">
              <span v-for="t in m.tags" :key="t" class="bb-tag">#{{ t }}</span>
            </span>
          </div>
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
})

defineEmits(['close'])

const { graphql } = useApi()

const tab = ref('inbox')
const loading = ref(false)
const sending = ref(false)
const inbox = ref([])
const journal = ref([])

const showCompose = ref(false)
const composeMode = ref('new')  // 'new' | 'reply'
const composeTitle = ref('')
const composeBody = ref('')
const composeTags = ref('')
const bodyEl = ref(null)

// Entity name cache for inbox senders
const senderNames = ref({})
const replyTarget = ref(null)
const replyName = ref('')

const QUERY_INBOX = `
  query($eid: ID!) {
    incomingMessages(entityId: $eid) {
      id senderEntityId body createdAt relationshipDescription tags
    }
  }
`

const QUERY_JOURNAL = `
  query($eid: ID!) {
    journal(entityId: $eid) {
      id title body createdAt tags
    }
  }
`

const SEND_LETTER = `
  mutation($sender: ID!, $recipient: ID!, $body: String!) {
    sendMessage(input: {
      senderEntityId: $sender
      recipientEntityId: $recipient
      kind: LETTER
      body: $body
    }) { id }
  }
`

const ADD_JOURNAL = `
  mutation($eid: ID!, $title: String!, $body: String!, $tags: [String!]) {
    addJournalEntry(input: {
      entityId: $eid
      title: $title
      body: $body
      tags: $tags
    }) { id }
  }
`

const composePlaceholder = computed(() => {
  if (composeMode.value === 'reply') return 'Write your reply…'
  if (tab.value === 'journal') return 'Write a journal entry…'
  return 'Write a letter…'
})

async function fetch() {
  if (!props.visible) return
  loading.value = true
  try {
    if (tab.value === 'inbox') {
      const data = await graphql(QUERY_INBOX, { eid: props.entityId })
      inbox.value = data?.incomingMessages || []
      // Resolve sender names
      for (const m of inbox.value) {
        if (!senderNames.value[m.senderEntityId]) {
          fetchEntityName(m.senderEntityId)
        }
      }
    } else {
      const data = await graphql(QUERY_JOURNAL, { eid: props.entityId })
      journal.value = data?.journal || []
    }
  } finally {
    loading.value = false
  }
}

async function fetchEntityName(eid) {
  try {
    const data = await graphql('{ entity(id: "' + eid + '") { name } }')
    if (data?.entity) senderNames.value[eid] = data.entity.name
  } catch { /* ignore */ }
}

function senderName(eid) {
  return senderNames.value[eid] || eid
}

async function send() {
  await nextTick()
  if (!composeBody.value.trim() || sending.value) return
  sending.value = true
  try {
    const body = composeBody.value.trim()
    if (tab.value === 'journal') {
      const tags = composeTags.value
        .split(',')
        .map(t => t.trim())
        .filter(Boolean)
      await graphql(ADD_JOURNAL, {
        eid: props.entityId,
        title: composeTitle.value.trim(),
        body: body,
        tags: tags.length ? tags : null,
      })
    } else if (composeMode.value === 'reply' && replyTarget.value) {
      await graphql(SEND_LETTER, {
        sender: props.entityId,
        recipient: replyTarget.value,
        body: body,
      })
    }
  } finally {
    sending.value = false
    cancelCompose()
    await fetch()
  }
}

function openCompose(mode) {
  if (mode === void 0) mode = 'new'
  composeMode.value = mode || 'new'
  showCompose.value = true
  nextTick(() => bodyEl.value?.focus())
}

function cancelCompose() {
  showCompose.value = false
  composeTitle.value = ''
  composeBody.value = ''
  composeTags.value = ''
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

function focusBody() {
  bodyEl.value?.focus()
}

function formatTime(iso) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleDateString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}

// Refetch when tab changes or panel opens
watch(tab, fetch)
watch(() => props.visible, (v) => { if (v) fetch() })
</script>

<style scoped>
.bluebook-backdrop {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: rgba(0,0,0,0.6);
  display: flex;
  align-items: center;
  justify-content: center;
}
.bluebook-panel {
  background: var(--bg-panel);
  backdrop-filter: blur(16px);
  border-radius: var(--radius);
  border: 1px solid var(--border);
  width: 480px;
  max-width: 95vw;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.bb-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}
.bb-header h2 {
  font-size: 16px;
  margin: 0;
}
.bb-close {
  background: none;
  border: none;
  color: var(--text-dim);
  font-size: 16px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
}
.bb-close:hover { background: var(--bg-hover); color: var(--text); }

.bb-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
}
.bb-tabs button {
  flex: 1;
  padding: 8px;
  background: none;
  border: none;
  color: var(--text-dim);
  font-size: 13px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: color 0.15s, border-color 0.15s;
}
.bb-tabs button.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}
.bb-tabs button:hover { color: var(--text); }

.bb-compose {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.bb-input {
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-input);
  color: var(--text);
  font-size: 12px;
  outline: none;
}
.bb-input:focus { border-color: var(--accent); }
.bb-tags { font-size: 11px; }
.bb-body-row {
  display: flex;
  gap: 6px;
}
.bb-textarea {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-input);
  color: var(--text);
  font-size: 12px;
  resize: none;
  outline: none;
  font-family: inherit;
}
.bb-textarea:focus { border-color: var(--accent); }
.bb-send {
  padding: 4px 12px;
  border: none;
  border-radius: 4px;
  background: var(--accent);
  color: #fff;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.bb-send:disabled { opacity: 0.4; cursor: default; }
.bb-send:not(:disabled):hover { opacity: 0.85; }

.bb-entries {
  flex: 1;
  overflow-y: auto;
  padding: 8px 12px;
}
.bb-empty {
  color: var(--text-dim);
  font-size: 13px;
  text-align: center;
  padding: 32px 0;
}
.bb-entry {
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.bb-entry:last-child { border-bottom: none; }
.bb-entry-header {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 4px;
}
.bb-sender {
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
}
.bb-rel {
  font-size: 11px;
  color: var(--text-dim);
  font-style: italic;
}
.bb-entry-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 2px;
}
.bb-body {
  font-size: 13px;
  color: var(--text);
  line-height: 1.4;
  white-space: pre-wrap;
}
.bb-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}
.bb-time {
  font-size: 10px;
  color: var(--text-dim);
}
.bb-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.bb-tag {
  font-size: 10px;
  color: var(--accent);
  opacity: 0.7;
}
</style>
