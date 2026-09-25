import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

/**
 * The stage's responsive layout gates. Phone-width layouts turn the bottom
 * sheet into three first-class bands (location / sheet / dice); wide landscape
 * layouts instead dock the sheet to the left of the map. This owns which of
 * those is active, and on mobile which band is focused, which bands are visible
 * at all, and the measured height the dice band needs.
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

  // The landscape dock: where the sheet stops riding in the roller's
  // bottom-centre column and sits beside it instead. Gated on width AND
  // orientation, because both conjuncts carry weight — a portrait tablet keeps
  // the pop-out (its column has height to spare), while orientation alone would
  // dock an iPhone SE in landscape (667×375) and leave it a 267px map.
  //
  // Deliberately NOT keyed on available height: every standard iPad landscape
  // viewport is ≥744px tall (1133×744 mini, 1180×820, 1194×834, 1366×1024), so
  // a height ceiling would never fire on a tablet in landscape — it would dock
  // only the phone-landscape case and refuse the tablet one.
  const dockMq = window.matchMedia(`(min-width: ${MOBILE_MAX_WIDTH + 1}px) and (orientation: landscape)`)
  const sheetDock = ref(false)
  function syncSheetDock() { sheetDock.value = dockMq.matches }
  syncSheetDock()
  dockMq.addEventListener('change', syncSheetDock)
  onUnmounted(() => dockMq.removeEventListener('change', syncSheetDock))

  // ── "Large height" ───────────────────────────────────────────────────
  // A second kind of gate, for callers that change *shape* rather than width:
  // the sheet's trait-set accordion is only for a sheet with height to spare
  // (the human's rule, 2026-09-25). Landscape alone is not enough — the phone
  // landscape dock is 390px tall — so height is the missing conjunct.
  //
  // Same threshold as the CSS rule that swaps in `--dock-w-short`
  // (`@media (max-height: 500px)`), deliberately: "short" should mean one thing
  // across the stage rather than two numbers free to drift apart.
  const shortViewport = ref(false)
  const shortMq = window.matchMedia('(max-height: 500px)')
  function syncShortViewport() { shortViewport.value = shortMq.matches }
  syncShortViewport()
  shortMq.addEventListener('change', syncShortViewport)
  onUnmounted(() => shortMq.removeEventListener('change', syncShortViewport))

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

  // Focus is user-driven only (a tap or a drag) — no auto-focus on phase
  // changes. (An earlier phase watcher yanked focus around rolls, which read as
  // panel jumps.)

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

  // ── Drag a teaser to open its band ───────────────────────────────────
  // The same gesture vocabulary as the dice panel's drag (App.vue's
  // PANEL_DRAG_*): a dead-zone, then the bands follow the finger, then the
  // release settles on flick velocity or distance, else reverts.
  //
  // The handle is the `.band-tap` capture layer already sitting over every
  // collapsed band — the same target a tap uses, so the two affordances cannot
  // drift apart. It is deliberately NOT the band body: the bands are full of
  // their own gestures (the roller's drag, travel dots, occupant drags, trait
  // grips and long-press), and a band-wide handle would fight all of them.
  //
  // Grabbing a teaser pulls THAT band open (not a neighbour step), which is
  // what the hand expects: you grab the thing you want and pull.
  const BAND_DRAG_SLOP = 8          // px: dead-zone so a tap is still a tap
  const BAND_DRAG_DISTANCE = 72     // px: drag far enough → open
  const BAND_DRAG_VELOCITY = 0.5    // px/ms: flick fast enough → open
  const BAND_INDEX = { location: 0, sheet: 1, dice: 2 }

  let bandDrag = null
  let bandSuppressUntil = 0

  function stageEl() {
    return wrapperEl.value?.closest('.stage') || null
  }

  function bandEls() {
    const stage = stageEl()
    if (!stage) return null
    const els = ['.loc-band', '.sheet-band', '.roller-band'].map((sel) => stage.querySelector(sel))
    return els.every(Boolean) ? els : null
  }

  const rectH = (el) => el.getBoundingClientRect().height

  /**
   * The heights the bands take in `target`, read off the real layout: swap the
   * focus class with transitions off for one synchronous frame, measure, swap
   * back. Measuring beats re-deriving the numbers — they live in CSS and differ
   * per state (`focus-dice` mixes percentages, a 56px sheet teaser and the
   * measured `--roller-h`; `:has(.kind-empty-pool)` and `sheet-empty` each
   * redistribute again). Nothing paints between the swap and the restore, so
   * this is invisible.
   */
  function measureFocus(target) {
    const stage = stageEl()
    const els = bandEls()
    if (!stage || !els) return null
    const cur = mobileFocus.value
    if (target === cur) return null
    const prev = els.map((el) => el.style.transition)
    els.forEach((el) => { el.style.transition = 'none' })
    stage.classList.remove(`focus-${cur}`)
    stage.classList.add(`focus-${target}`)
    const heights = els.map(rectH)
    stage.classList.remove(`focus-${target}`)
    stage.classList.add(`focus-${cur}`)
    els.forEach((el, i) => { el.style.transition = prev[i] })
    return heights
  }

  function stopBandDrag(suppressClick) {
    if (suppressClick) bandSuppressUntil = Date.now() + 250
    document.removeEventListener('touchmove', onBandDragMove)
    document.removeEventListener('touchend', onBandDragEnd)
    document.removeEventListener('touchcancel', onBandDragEnd)
    bandDrag = null
  }

  function onBandDragStart(e, focus) {
    if (!mobileStackActive.value) return
    if (focus === 'sheet' && sheetEmpty.value) return
    // A GM panel takes the whole stage; there is no stack to drag.
    if (document.querySelector('.panel-viewport')) return
    const touch = e.touches?.[0]
    if (!touch) return
    bandDrag = {
      focus,
      index: BAND_INDEX[focus],
      startY: touch.clientY,
      lastY: touch.clientY,
      lastT: performance.now(),
      velocity: 0,
      started: false,
      els: null,
      from: null,
      to: null,
      delta: 0,
    }
    document.addEventListener('touchmove', onBandDragMove, { passive: false })
    document.addEventListener('touchend', onBandDragEnd)
    document.addEventListener('touchcancel', onBandDragEnd)
  }

  function onBandDragMove(e) {
    const d = bandDrag
    if (!d) return
    const touch = e.touches?.[0]
    if (!touch) return
    const y = touch.clientY
    const dy = Math.abs(y - d.startY)

    if (!d.started) {
      if (dy < BAND_DRAG_SLOP) return          // wait for the finger to commit
      const els = bandEls()
      const from = els && els.map(rectH)
      const to = measureFocus(d.focus)
      if (!els || !from || !to || to[d.index] <= from[d.index]) {
        stopBandDrag(true)                     // nothing to open; swallow the tap
        return
      }
      d.started = true
      d.els = els
      d.from = from
      d.to = to
      d.delta = to[d.index] - from[d.index]
      els.forEach((el) => { el.style.transition = 'none' })
    }

    e.preventDefault()                         // the stack does not scroll
    const now = performance.now()
    const dt = now - d.lastT
    if (dt > 0) {
      const inst = Math.abs(y - d.lastY) / dt
      d.velocity = d.velocity * 0.75 + inst * 0.25
    }
    d.lastY = y
    d.lastT = now

    // Progress is the finger's own distance over the band's, so the band tracks
    // it 1:1 and is never outrun — the dice panel's rule.
    const p = Math.min(1, dy / d.delta)
    d.els.forEach((el, i) => {
      el.style.flexBasis = `${d.from[i] + (d.to[i] - d.from[i]) * p}px`
    })
  }

  function onBandDragEnd() {
    const d = bandDrag
    if (!d) return
    if (!d.started) { stopBandDrag(false); return }  // a tap: let its click through
    const moved = Math.abs(d.lastY - d.startY)
    if (moved >= BAND_DRAG_DISTANCE || d.velocity >= BAND_DRAG_VELOCITY) setMobileFocus(d.focus)
    stopBandDrag(true)
    // Hand the bands back to the focus classes. Re-enable the transition first
    // and drop the inline basis a frame later: clearing both at once changes the
    // value and the transition property together, and the browser snaps instead
    // of animating.
    nextTick(() => {
      d.els.forEach((el) => { el.style.transition = '' })
      requestAnimationFrame(() => {
        d.els.forEach((el) => { el.style.flexBasis = '' })
      })
    })
  }

  /** A tap on a teaser — suppressed when it is really the end of a drag. */
  function tapBand(focus) {
    if (Date.now() < bandSuppressUntil) return
    setMobileFocus(focus)
  }

  onUnmounted(() => { if (bandDrag) stopBandDrag(false) })

  return {
    isMobile, mobileFocus, mobileStackActive, sheetDock, sheetEmpty, setMobileFocus,
    shortViewport, rollerContentH, syncRollerContentH,
    onBandDragStart, tapBand,
  }
}
