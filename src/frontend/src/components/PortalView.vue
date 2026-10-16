<script setup>
/**
 * The portal — sign in, and your campaigns (B256).
 *
 * This is the **apex** surface: `transversal.app/portal` (the VPS rewrites the
 * apex `/` here). Campaigns live on their own hosts, `<slug>.<base-domain>`, and
 * this page is how you get to them.
 *
 * It talks to the account tier directly (`/api/v1/accounts/*`, `/api/v1/forks`)
 * rather than through GraphQL: those routes are the account tier, they are plain
 * REST, and the game's GraphQL schema has nothing to say about accounts.
 */
import { onMounted, ref } from 'vue'

const API = '/api/v1'

const loading = ref(true)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const account = ref(null)
const forks = ref([])
const email = ref('')
const newName = ref('')
/** The machine that runs Transversal is away (B88).
 *
 * A page nobody has loaded cannot be helped by the edge's offline page, so a tab that
 * is already open has to say this itself. Distinguished from an ordinary failure on
 * purpose: `401` is a legitimate account-tier answer ("not signed in"), while a thrown
 * fetch or a `5xx` means the multiverse is not answering at all. */
const away = ref(false)

async function call(path, { method = 'GET', body } = {}) {
  let response
  try {
    response = await fetch(`${API}${path}`, {
      method,
      credentials: 'same-origin',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch (e) {
    away.value = true
    throw e
  }
  if (response.status >= 500) away.value = true
  else away.value = false
  let payload = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }
  return { ok: response.ok, status: response.status, payload }
}

/** One neutral answer for both links, because the registry must not become a
 *  directory of who has an account. */
const NEUTRAL = 'If that address can receive mail, a link is on its way.'

function attune() {
  window.location.reload()
}

async function loadAccount() {
  const { ok, payload } = await call('/accounts/session')
  account.value = ok && payload?.signed_in ? payload.account : null
  if (account.value) await loadForks()
}

async function loadForks() {
  const { ok, payload } = await call('/forks')
  forks.value = ok && Array.isArray(payload) ? payload : []
}

async function withBusy(fn) {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await fn()
  } catch (e) {
    error.value = e?.message || 'something went wrong'
  } finally {
    busy.value = false
  }
}

function requestLink(path) {
  return withBusy(async () => {
    const address = email.value.trim()
    if (!address) {
      error.value = 'an email address is required'
      return
    }
    const { ok, payload } = await call(path, { method: 'POST', body: { email: address } })
    if (!ok) {
      error.value = payload?.detail || 'that did not work'
      return
    }
    notice.value = NEUTRAL
  })
}

function createFork() {
  return withBusy(async () => {
    const name = newName.value.trim()
    if (!name) {
      error.value = 'a name is required'
      return
    }
    const { ok, payload } = await call('/forks', { method: 'POST', body: { name } })
    if (!ok) {
      error.value = payload?.detail || 'that did not work'
      return
    }
    newName.value = ''
    notice.value = `“${payload.name}” is ready.`
    await loadForks()
  })
}

/** The link is single-use and short-lived, and it is what crosses to the fork's
 *  own host — the account session never goes there. */
function enter(fork) {
  return withBusy(async () => {
    const { ok, payload } = await call(`/forks/${fork.id}/enter`, { method: 'POST' })
    if (!ok) {
      error.value = payload?.detail || 'that did not work'
      return
    }
    window.location.href = payload.enter_url
  })
}

function signOut() {
  return withBusy(async () => {
    await call('/accounts/sign-out', { method: 'POST' })
    account.value = null
    forks.value = []
    notice.value = 'Signed out.'
  })
}

onMounted(async () => {
  await loadAccount()
  loading.value = false
})
</script>

<template>
  <div class="portal">
    <header>
      <h1>Transversal</h1>
      <p class="tagline">Your multiverse. Your table.</p>
    </header>

    <p v-if="loading" class="muted">Loading…</p>

    <template v-else>
      <!-- The multiverse is not answering. A sign-in form here would be a lie: the
           form cannot work either, and "wrong password"-shaped failure is the worst
           possible reading. Same words as the edge's page, since it is the same
           condition seen from a tab that was already open. -->
      <section v-if="away" class="card">
        <h2>No universes within resonance</h2>
        <p class="muted">
          The multiverse is not answering, and there is insufficient razmerit here to
          hold the attunement. Re-attune shortly — the carrier should resolve on its
          own.
        </p>
        <div class="row">
          <button @click="attune">Attune again</button>
        </div>
      </section>

      <!-- Signed out: one address, two links. -->
      <section v-else-if="!account" class="card">
        <h2>Sign in or create an account</h2>
        <p class="muted">
          We email you a single-use link. No password to remember, and nothing to
          lose.
        </p>
        <label for="email">Email address</label>
        <input
          id="email"
          v-model="email"
          type="email"
          autocomplete="email"
          placeholder="you@example.com"
          :disabled="busy"
          @keyup.enter="requestLink('/accounts/sign-in')"
        />
        <div class="row">
          <button :disabled="busy" @click="requestLink('/accounts/register')">
            Create account
          </button>
          <button class="secondary" :disabled="busy" @click="requestLink('/accounts/sign-in')">
            Sign in
          </button>
        </div>
        <p v-if="notice" class="notice">{{ notice }}</p>
        <p v-if="error" class="error">{{ error }}</p>
      </section>

      <!-- Signed in: your campaigns. -->
      <section v-else class="card">
        <div class="row space">
          <h2>Your campaigns</h2>
          <button class="link" :disabled="busy" @click="signOut">Sign out</button>
        </div>
        <p class="muted">{{ account.email }}</p>

        <ul v-if="forks.length" class="forks">
          <li v-for="fork in forks" :key="fork.id">
            <div>
              <strong>{{ fork.name }}</strong>
              <span v-if="fork.url" class="muted"> · {{ fork.url }}</span>
              <span v-else class="muted"> · {{ fork.database }}</span>
            </div>
            <button :disabled="busy" @click="enter(fork)">Enter</button>
          </li>
        </ul>
        <p v-else class="muted">
          No campaigns yet. Create one — it is a copy of the global multiverse, and
          it is yours.
        </p>

        <label for="new-name">New campaign</label>
        <div class="row">
          <input
            id="new-name"
            v-model="newName"
            placeholder="The Varenya Campaign"
            :disabled="busy"
            @keyup.enter="createFork"
          />
          <button :disabled="busy" @click="createFork">Create</button>
        </div>
        <p v-if="notice" class="notice">{{ notice }}</p>
        <p v-if="error" class="error">{{ error }}</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.portal {
  max-width: 34rem;
  margin: 0 auto;
  padding: 4rem 1.25rem 6rem;
  color: #e8e6f0;
}
header {
  text-align: center;
  margin-bottom: 2rem;
}
h1 {
  margin: 0;
  font-size: 2rem;
  letter-spacing: 0.04em;
}
.tagline {
  margin: 0.35rem 0 0;
  color: #9a95ad;
}
.card {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: 0.9rem;
  padding: 1.4rem;
}
h2 {
  margin: 0 0 0.35rem;
  font-size: 1.1rem;
}
label {
  display: block;
  margin: 1rem 0 0.35rem;
  font-size: 0.85rem;
  color: #b9b4c9;
}
input {
  width: 100%;
  box-sizing: border-box;
  padding: 0.6rem 0.7rem;
  border-radius: 0.5rem;
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(0, 0, 0, 0.3);
  color: inherit;
  font: inherit;
}
.row {
  display: flex;
  gap: 0.6rem;
  align-items: center;
  margin-top: 0.75rem;
}
.row.space {
  justify-content: space-between;
}
button {
  padding: 0.55rem 0.9rem;
  border-radius: 0.5rem;
  border: 1px solid transparent;
  background: #6c5ce7;
  color: #fff;
  font: inherit;
  cursor: pointer;
}
button.secondary {
  background: transparent;
  border-color: rgba(255, 255, 255, 0.25);
  color: inherit;
}
button.link {
  background: none;
  border: none;
  color: #9a95ad;
  padding: 0;
}
button:disabled {
  opacity: 0.55;
  cursor: default;
}
.forks {
  list-style: none;
  margin: 0.75rem 0 0;
  padding: 0;
}
.forks li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  padding: 0.6rem 0;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}
.muted {
  color: #9a95ad;
  font-size: 0.9rem;
}
.notice {
  color: #7bd88f;
  font-size: 0.9rem;
}
.error {
  color: #ff8b8b;
  font-size: 0.9rem;
}
</style>
