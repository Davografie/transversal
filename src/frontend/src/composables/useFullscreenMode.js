import { computed, ref, watch } from 'vue'
import { useFullscreen } from '@vueuse/core'

/**
 * Fullscreen, as a **per-device preference** with a policy on top.
 *
 * Why it exists: the app shell is `html, body, #app { overflow: hidden }` with
 * every scroll inside a band or a panel, so the document never scrolls — and
 * the browser only retracts its address bar on a document scroll. On a phone
 * the bar is therefore permanent, and it is chrome the play surface never gets
 * back. `100dvh` keeps the layout *honest* about the space that is left; this
 * is what reclaims it ([[UI-UX Design#Fullscreen]]).
 *
 * The API is VueUse's `useFullscreen` (prefixed-API handling and the reactive
 * `fullscreenchange` read). Everything that is a *decision* is here, because a
 * library cannot know when entering would be rude:
 *
 * 1. **`off` / `on` / `auto`.** `auto` means "on a touch device, be fullscreen
 *    as much as possible"; a mouse/keyboard device is left alone.
 * 2. **The entry point is a completed interaction.** Fullscreen changes the
 *    viewport height, which re-derives every band's percentage, the roller's
 *    measured height and the location camera's zoom. Doing that on `pointerdown`
 *    lands the re-layout *between* a finger touching and lifting, which can
 *    retarget the tap the player meant. So it rides `click` (and `keydown`),
 *    after the interaction has resolved.
 * 3. **A user's exit is respected.** The back gesture exists so the player can
 *    reach another tab or app; re-entering straight away would trap them. An
 *    exit sets `suppressed` until the page is next hidden and shown again — by
 *    which time the exit has done its job — and an explicit mode change always
 *    wins over it.
 * 4. **We only ever leave when the player says `off`.** Switching input device
 *    (a tablet gaining a keyboard) stops *entering*; it never yanks fullscreen
 *    away from someone who is using it.
 *
 * The device kind is **remembered per device** (`localStorage`) from the last
 * input actually used, because a media query can only guess on a convertible:
 * on load it is `(hover: none) and (pointer: coarse)`, and the first real
 * `pointerdown` / `keydown` overwrites it. A pen counts as touch — no keyboard
 * in hand.
 */

const MODE_KEY = 'fullscreenMode'
const INPUT_KEY = 'inputKind'

export const FULLSCREEN_MODES = ['off', 'on', 'auto']
const INPUT_KINDS = ['touch', 'pointer']

const UNSUPPORTED_HINT =
  'This browser has no fullscreen for a page — on an iPhone, add Transversal to your Home Screen instead.'

function read(key, valid, fallback) {
  try {
    const v = localStorage.getItem(key)
    return valid.includes(v) ? v : fallback
  } catch {
    return fallback
  }
}

function write(key, v) {
  try {
    localStorage.setItem(key, v)
  } catch {
    /* private mode, a full quota — a preference that cannot persist is not a fault */
  }
}

/** The first guess, before anyone has touched anything. */
function guessInputKind() {
  try {
    return window.matchMedia('(hover: none) and (pointer: coarse)').matches ? 'touch' : 'pointer'
  } catch {
    return 'pointer'
  }
}

// Module-level singleton: the settings block and the app-wide entry policy have
// to share one answer (the shape `useMediaQuality` uses for the same reason).
// The default is `off` — fullscreen is a behaviour change nobody asked for
// until they choose it.
const mode = ref(read(MODE_KEY, FULLSCREEN_MODES, 'off'))
const inputKind = ref(read(INPUT_KEY, INPUT_KINDS, guessInputKind()))
/** Set by a *user* exit; cleared when they come back to the page. */
const suppressed = ref(false)

let api = null

// The standard, decisive signal. VueUse's own `isSupported` also accepts the
// legacy prefixed aliases (`webkitRequestFullscreen`), which iPhone Safari has
// on `<video>` but not on an element — so it reports support where a page
// cannot actually go fullscreen. `document.fullscreenEnabled` does not.
const isSupported = computed(
  () =>
    !!api?.isSupported.value &&
    typeof document !== 'undefined' &&
    document.fullscreenEnabled === true
)

const isFullscreen = computed(() => !!api?.isFullscreen.value)

/**
 * The whole policy, as a pure function — every branch is exercisable without a
 * browser (`scripts/check-fullscreen.mjs`).
 */
export function shouldEnter({ mode, inputKind, supported, fullscreen, suppressed, visible }) {
  if (!supported || !visible || fullscreen || suppressed) return false
  if (mode === 'off') return false
  if (mode === 'on') return true
  return inputKind === 'touch' // 'auto'
}

async function tryEnter() {
  if (
    !shouldEnter({
      mode: mode.value,
      inputKind: inputKind.value,
      supported: isSupported.value,
      fullscreen: isFullscreen.value,
      suppressed: suppressed.value,
      visible: typeof document === 'undefined' || document.visibilityState === 'visible',
    })
  )
    return
  try {
    await api.enter()
  } catch {
    // No transient activation, or the browser refused. A refused fullscreen is
    // a normal outcome, not a fault: stay as we are and try again on the next
    // interaction. Swallowing it is what keeps this out of the console.
  }
}

function setInputKind(v) {
  if (inputKind.value === v) return
  inputKind.value = v
  write(INPUT_KEY, v)
}

function onPointerDown(e) {
  // touch + pen are both "a finger, no keyboard in hand"
  setInputKind(e.pointerType === 'mouse' ? 'pointer' : 'touch')
}

function onKeyboard() {
  setInputKind('pointer')
  tryEnter()
}

function onVisibility() {
  // Back in the app: the suppression has done its job, so auto re-arms.
  if (document.visibilityState === 'visible') suppressed.value = false
}

const hint = computed(() => {
  if (!isSupported.value) return UNSUPPORTED_HINT
  if (mode.value === 'off') return 'The browser keeps its address bar.'
  // The state the *player* cannot otherwise see: they left, and we are holding
  // off. Saying so is what makes tapping the same segment again meaningful.
  if (suppressed.value && !isFullscreen.value)
    return 'Left fullscreen — tap here again, or switch away and back, to resume.'
  if (mode.value === 'on') return 'Always fullscreen — the back gesture still leaves it.'
  return inputKind.value === 'touch'
    ? 'Touch screen detected — the app goes fullscreen when you tap.'
    : 'Mouse or keyboard detected — Auto leaves the browser alone.'
})

/** The segments the settings control renders, disabled (with the reason in the
 *  hint) when the browser cannot do it at all — the app's "why not" convention. */
const options = computed(() => [
  { value: 'off', label: 'Off' },
  {
    value: 'on',
    label: 'On',
    disabled: !isSupported.value,
    title: isSupported.value ? 'Always fullscreen' : UNSUPPORTED_HINT,
  },
  {
    value: 'auto',
    label: 'Auto',
    disabled: !isSupported.value,
    title: isSupported.value ? 'Fullscreen on touch devices' : UNSUPPORTED_HINT,
  },
])

function setMode(v) {
  if (!FULLSCREEN_MODES.includes(v)) return
  mode.value = v
  write(MODE_KEY, v)
  // An explicit choice outranks a previous exit.
  suppressed.value = false
  if (v === 'off') {
    api.exit().catch(() => {})
    return
  }
  // The click that chose this is itself the gesture that permits entering.
  tryEnter()
}

function install() {
  if (typeof document === 'undefined') return
  document.addEventListener('click', tryEnter, true)
  window.addEventListener('keydown', onKeyboard, true)
  window.addEventListener('pointerdown', onPointerDown, true)
  document.addEventListener('visibilitychange', onVisibility)
  watch(api.isFullscreen, (now, was) => {
    if (was && !now) suppressed.value = true
  })
}

export function useFullscreenMode() {
  if (!api) {
    api = useFullscreen()
    install()
  }
  return { mode, setMode, options, hint, inputKind, isSupported, isFullscreen, suppressed }
}
