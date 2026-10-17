import { ref } from 'vue'

// ── Module-level state ──────────────────────────────
// One request for the whole app: every surface that offers a GPU action reads the
// same answer, and they mount at different times (the entity editor, the trait
// gallery, the sheet's instance editor).
const gpuJobs = ref(true)
const reason = ref('')
let pending = null

/** The short form, for a surface with room for a line but not a sentence. */
export const GPU_OFF_NOTE = 'GPU tools are off on this deployment.'

/**
 * What this deployment will spend the GPU on ([[B88]]).
 *
 * `GPU_JOBS=off` refuses generation, animation, cut-out and upscale with a 503 and
 * stops an upload queuing a matte. That is the owner's switch and the **server's**
 * to state — a client must not guess it from an error. Buttons the guard would
 * refuse are disabled, with the reason in the tooltip, instead of being offered and
 * then rejected: a greyed button is a surface telling the truth.
 *
 * Optimistic until told, and if the read fails: "unset means on" is the server's
 * rule, and a capabilities request that cannot be made must never lock a
 * GPU-enabled deployment out of its own tools.
 */
export function useCapabilities() {
  function load() {
    if (!pending) {
      pending = fetch('/api/v1/capabilities')
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (data && typeof data.gpu_jobs === 'boolean') {
            gpuJobs.value = data.gpu_jobs
            reason.value = data.reason || ''
          }
        })
        .catch(() => { /* the optimistic default stands */ })
    }
    return pending
  }

  return { gpuJobs, reason, load }
}
