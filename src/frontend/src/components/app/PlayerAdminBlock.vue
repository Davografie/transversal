<template>
  <!-- SEC-3: the owner's roster, with the two acts that change it. Architects are
       included, because moving the architect line requires seeing who holds it. -->
  <div class="admin-block">
    <label class="settings-label">Players ({{ players.length }})</label>
    <div class="admin-list">
      <div v-for="p in players" :key="p.id" class="admin-row">
        <span class="admin-name">{{ p.name || p.id }}</span>
        <span class="admin-role" :class="{ arch: p.role === 'architect' }">{{ p.role }}</span>
        <button
          v-if="p.role !== 'architect'"
          class="admin-btn"
          :disabled="busy"
          @click="$emit('set-role', p.id, 'architect')"
        >Make architect</button>
        <button
          v-else
          class="admin-btn"
          :disabled="busy"
          @click="$emit('set-role', p.id, 'player')"
        >Demote</button>
        <!-- Two-step: revoking ends their sessions, which is not something to do
             by mis-click while a game is running. -->
        <button
          v-if="confirmId !== p.id"
          class="admin-btn danger"
          :disabled="busy"
          @click="confirmId = p.id"
        >Revoke</button>
        <button
          v-else
          class="admin-btn danger"
          :disabled="busy"
          @click="confirmId = ''; $emit('revoke', p.id)"
        >Really revoke?</button>
      </div>
    </div>
    <p v-if="notice" class="name-hint">{{ notice }}</p>
    <p v-if="error" class="switch-error">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  players: { type: Array, default: () => [] },
  busy: { type: Boolean, default: false },
  error: { type: String, default: '' },
  notice: { type: String, default: '' },
})

defineEmits(['revoke', 'set-role'])

const confirmId = ref('')
</script>

<style scoped>
.admin-block { width: 100%; }
.admin-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 220px;
  overflow-y: auto;
}
.admin-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.admin-name { flex: 1; text-align: left; }
.admin-role {
  color: var(--text-dim);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.admin-role.arch { color: var(--accent); }
.admin-btn {
  font-size: 11px;
  padding: 3px 8px;
  background: var(--overlay-6);
  border: 1px solid var(--overlay-8);
  border-radius: var(--radius-sm);
  color: var(--text-dim);
  cursor: pointer;
}
.admin-btn.danger { border-color: var(--danger); color: var(--danger); }
</style>
