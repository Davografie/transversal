import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

/**
 * The mobile focus stack: phone-width layouts turn the bottom sheet into three
 * first-class bands (location / sheet / dice). This owns which band is focused,
 * which bands are visible at all, and the measured height the dice band needs.
 *
 * `wrapperEl` is the `.dice-panel-wrapper` template ref — the roller is measured
 * through it, so the caller must pass the real ref, not a copy.
 */
export function useMobileBands({ wrapperEl, gmMode, entityId, viewingEntityId }) {
  const MOBILE_MAX_WIDTH = 820
  const isMobile = ref(false)
  const mobileFocus = ref('location')  // 'location' | 'sheet' | 'dice'

  const mobileMq = window.matchMedia(`(max-width: ${MOBILE_MAX_WIDTH}px)`)
  function syncIsMobile() { isMobile.value = mobileMq.matches }
  syncIsMobile()
  mobileMq.addEventListener('change', syncIsMobile)
  onUnmounted(() => mobileMq.removeEventListener('change', syncIsMobile))

  const mobileStackActive = computed(() => isMobile.value)

  // GM with no acting/viewed entity has an empty sheet band on mobile — it is
  // fully collapsed (peers bar is enough) and the sheet focus is unreachable.
  const sheetEmpty = computed(() => mobileStackActive.value && gmMode.value && !entityId.value && !viewingEntityId.value)
  watch(sheetEmpty, (v) => { if (v && mobileFocus.value === 'sheet') mobileFocus.value = 'location' })

  function setMobileFocus(f) {
    if (f === 'location' || f === 'sheet' || f === 'dice') {
      if (f === 'sheet' && sheetEmpty.value) return
      mobileFocus.value = f
    }
  }

  // Focus is tap-driven only — no auto-focus on phase changes. (An earlier
  // phase watcher yanked focus around rolls, which read as panel jumps.)

  // The mobile dice-focus band sizes to the roller's CONTENT as a concrete
  // length (keyword flex-basis: auto doesn't interpolate, which made entering /
  // leaving dice focus jump). --roller-h feeds the clamp() in styles.css.
  //
  // Measured as the flex column's INTRINSIC height (children + gaps + padding),
  // not `scrollHeight`: once the band has grown, scrollHeight reports the
  // element's own height, so the band would latch open after a wizard closes.
  const rollerContentH = ref(148)
  function syncRollerContentH() {
    const roller = wrapperEl.value?.querySelector('.dice-roller')
    if (!roller) return
    const rs = getComputedStyle(roller)
    const gap = parseFloat(rs.rowGap) || 0
    let h = (parseFloat(rs.paddingTop) || 0) + (parseFloat(rs.paddingBottom) || 0)
    const kids = [...roller.children].filter((el) => {
      const cs = getComputedStyle(el)
      return cs.display !== 'none' && cs.position !== 'absolute' && cs.position !== 'fixed'
    })
    kids.forEach((el, idx) => {
      const cs = getComputedStyle(el)
      h += el.getBoundingClientRect().height
        + (parseFloat(cs.marginTop) || 0) + (parseFloat(cs.marginBottom) || 0)
      if (idx < kids.length - 1) h += gap
    })
    rollerContentH.value = Math.max(0, Math.round(h))
  }
  watch(mobileFocus, () => nextTick(syncRollerContentH))
  watch(isMobile, () => nextTick(syncRollerContentH))
  onMounted(() => {
    const roller = wrapperEl.value?.querySelector('.dice-roller')
    if (!roller) return
    syncRollerContentH()
    const mo = new MutationObserver(syncRollerContentH)
    mo.observe(roller, { subtree: true, childList: true, attributes: true, characterData: true })
    window.addEventListener('resize', syncRollerContentH)
    onUnmounted(() => {
      mo.disconnect()
      window.removeEventListener('resize', syncRollerContentH)
    })
  })

  return { isMobile, mobileFocus, mobileStackActive, sheetEmpty, setMobileFocus, rollerContentH, syncRollerContentH }
}
