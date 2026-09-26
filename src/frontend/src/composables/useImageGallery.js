/**
 * One owner's pictures, and every action that changes them ([[B211]]).
 *
 * Before this there were three copies of the same work: the entity editor, the
 * trait editor and the viewer each fetched the list, toggled roles, toggled
 * flags, started a cut-out or an upscale, and polled `/imagen/jobs` — and they had
 * drifted (one upload still sent the legacy `entity_id`, one poller knew about
 * `upscale` and another did not). One picture, so one implementation.
 *
 * The owner is passed as a **getter** because a panel's id arrives as a prop and
 * changes under it; `{ kind: 'entity' | 'trait', id, universe? }`.
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

/**
 * Upload one file to an owner. The one upload implementation.
 *
 * `owner_kind`/`owner_id` are the current contract (`entity_id` is still accepted
 * by the server for older callers, but nothing here uses it); `universe` matters
 * for a trait, whose pictures are stored in a universe for provenance, and
 * `flags` lets an upload declare `ai` for art whose workflow the author knows.
 */
export async function uploadImage({ kind, id, universe = '', flags = '', variantId = '', file }) {
  const params = new URLSearchParams({ owner_kind: kind, owner_id: id })
  if (universe) params.set('universe', universe)
  if (flags) params.set('flags', flags)
  // A picture can sit one rung below its owner — a **traitsetting** overriding
  // the registry trait's picture, exactly as a projection overrides an entity's.
  // The id is a record id (it may contain a colon); it never names a file.
  if (variantId) params.set('variant_id', variantId)
  const body = new FormData()
  body.append('file', file)
  const res = await fetch(`/api/v1/media/upload?${params}`, { method: 'POST', body })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || `Upload failed (${res.status})`)
  // The server writes the file best-effort and returns a null id when it could
  // not attach it — an upload that silently did nothing is the failure worth
  // naming rather than swallowing.
  if (!data.image_id) throw new Error('The file was saved but not attached to the owner.')
  return data
}

/**
 * Copy an existing picture onto another rung ([[B215]]).
 *
 * The instance editor uses this to take one of the **trait's** pictures as this
 * instance's override. The server copies the files rather than sharing them,
 * because a rung's URL comes from its own record's filename.
 */
export async function copyImage({ imageId, ownerKind, ownerId, variantId = '' }) {
  const params = new URLSearchParams({
    image_id: imageId, owner_kind: ownerKind, owner_id: ownerId,
  })
  if (variantId) params.set('variant_id', variantId)
  const res = await fetch(`/api/v1/media/copy?${params}`, { method: 'POST' })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || `Copy failed (${res.status})`)
  if (!data.image_id) throw new Error('The copy was not attached to this trait.')
  return data
}

export function useImageGallery(owner, { pollMs = 2000, filter = null } = {}) {
  const images = ref([])
  const loading = ref(false)
  const error = ref('')
  /** The owner's active media job, if any: one registry, keyed by owner id. */
  const job = ref(null)
  /** Which action is in flight — `'' | 'upload' | 'cutout' | 'upscale' | 'delete'`. */
  const busy = ref('')

  const ownerId = () => (typeof owner === 'function' ? owner()?.id : owner?.id) || ''
  const ownerKind = () => (typeof owner === 'function' ? owner()?.kind : owner?.kind) || 'entity'
  const ownerUniverse = () => (typeof owner === 'function' ? owner()?.universe : owner?.universe) || ''

  const listUrl = () => `/api/v1/imagen/${encodeURIComponent(ownerId())}`

  async function load() {
    if (!ownerId()) { images.value = []; return images.value }
    loading.value = true
    try {
      const res = await fetch(listUrl())
      const data = res.ok ? await res.json() : { images: [] }
      const rows = data.images || []
      images.value = filter ? rows.filter(filter) : rows
    } catch {
      images.value = []
    } finally {
      loading.value = false
    }
    return images.value
  }

  async function run(name, fn) {
    busy.value = name
    error.value = ''
    try {
      return await fn()
    } catch (e) {
      error.value = e?.message || 'Request failed'
      return null
    } finally {
      busy.value = ''
    }
  }

  async function patch(imageId, body, what) {
    if (!imageId) return null
    return run(what, async () => {
      const res = await fetch(`/api/v1/imagen/${encodeURIComponent(imageId)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(`${what} failed (${res.status})`)
      await load()
      return true
    })
  }

  const setRoles = (imageId, roles) => patch(imageId, { roles }, 'Tag')
  const setFlags = (imageId, flags) => patch(imageId, { flags }, 'Tag')
  /** Move a picture between rungs: the entity's own images, or a projection's. */
  const assignTo = (imageId, projectionId) => patch(imageId, { projection_id: projectionId || null }, 'Move')

  // Roles are unique per (owner, role), so assigning one strips it from a sibling
  // picture: ticking a box here MOVES the tag. Flags never strip anything.
  function toggleRole(image, role) {
    const current = image?.roles || []
    return setRoles(image.id, current.includes(role) ? current.filter(r => r !== role) : [...current, role])
  }

  function toggleFlag(image, flag) {
    const current = image?.flags || []
    return setFlags(image.id, current.includes(flag) ? current.filter(f => f !== flag) : [...current, flag])
  }

  async function cutOut(imageId) {
    if (!imageId) return null
    return run('cutout', async () => {
      const res = await fetch(
        `/api/v1/remove-background/${encodeURIComponent(ownerId())}?owner_kind=${encodeURIComponent(ownerKind())}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image_id: imageId }),
        },
      )
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || `Cut out failed (${res.status})`)
      await pollJob()
      return true
    })
  }

  async function upscale(imageId) {
    if (!imageId) return null
    return run('upscale', async () => {
      const res = await fetch(`/api/v1/upscale/${encodeURIComponent(imageId)}`, { method: 'POST' })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || `Upscale failed (${res.status})`)
      await pollJob()
      return true
    })
  }

  async function remove(imageId) {
    if (!imageId) return null
    return run('delete', async () => {
      const res = await fetch(`/api/v1/imagen/${encodeURIComponent(imageId)}`, { method: 'DELETE' })
      if (!res.ok) throw new Error(`Delete failed (${res.status})`)
      await load()
      return true
    })
  }

  async function pollJob() {
    if (!ownerId()) return
    try {
      const res = await fetch('/api/v1/imagen/jobs')
      if (!res.ok) return
      const jobs = (await res.json()).jobs || {}
      job.value = jobs[ownerId()] || null
    } catch { /* best-effort: a missing job list just leaves the buttons enabled */ }
  }

  /** The owner's job of one type — `animate` / `remove_bg` / `upscale` / `imagen`. */
  const jobFor = (type) => (job.value && job.value.type === type ? job.value : null)

  watch(() => ownerId(), load, { immediate: true })

  let _timer = null
  onMounted(() => {
    pollJob()
    if (pollMs) _timer = setInterval(pollJob, pollMs)
  })
  onUnmounted(() => { if (_timer) clearInterval(_timer) })

  // A job that ends produced a file: re-read so the gallery shows it.
  watch(job, async (now, prev) => {
    if (prev && !now) await load()
  })

  const count = computed(() => images.value.length)

  return {
    images, loading, error, job, busy, count,
    load, remove, setRoles, setFlags, toggleRole, toggleFlag,
    assignTo, cutOut, upscale, pollJob, jobFor,
  }
}
