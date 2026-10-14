import { computed, onUnmounted, ref, useId, watch } from 'vue'

/**
 * Headless suggestion list for the autocomplete surfaces.
 *
 * Three components grew the same list mechanics separately — `SearchDropdown`
 * (single-select typeahead), `TagInput` (multi-value chips) and `TargetPicker`
 * (the server-driven picker built on SearchDropdown). The mechanics are the
 * fiddly, bug-prone half: normalising options, filtering against what is already
 * chosen, arming and walking a highlight, the create row, the aria wiring, and
 * fetching suggestions. The markup is *not* shared, and should not be: a
 * single-select input and a chip field have different DOM and different commit
 * semantics. So this owns the list; the shells own the rendering.
 *
 * **Options may be a plain array or a query function.** A function is taken as
 * a server-backed source: it is called with the current query text (debounced)
 * and may return a promise. That is what lets a multi-select work over a
 * vocabulary too large to preload, which is the thing the array-only shape
 * could not express.
 *
 * See [[UI-UX Design#Autocomplete core]].
 */
export function useCombobox({
  /** Ref of an array of options, or of `(query) => options | Promise<options>`. */
  options,
  /** Ref of the text being typed. */
  query,
  /** Ref of value(s) already chosen — always excluded from the list. */
  chosen = ref([]),
  /** Maps a source entry to `{ value, label, hint?, raw }`. */
  normalize = (o) => ({
    value: o?.value ?? o,
    label: o?.label ?? String(o ?? ''),
    hint: o?.hint,
    raw: o,
  }),
  /** Extra values to exclude beyond `chosen` (SearchDropdown's `excludeIds`). */
  exclude = ref([]),
  /** Whether free text that matches nothing may still be committed. */
  allowCustom = false,
  /** Label for the create row. */
  createLabel = (t) => `Create “${t}”`,
  /** 0 = no limit. */
  maxResults = 0,
  /**
   * Reveal the list one page at a time instead of all at once (0 = all at once),
   * grown by {@link loadMore} — the shell calls it when its list is scrolled to
   * the end. For a match set that can run to hundreds of rows, where `maxResults`
   * would silently *hide* the rest: the window is a rendering decision, the list
   * is still the whole match set, and `hasMore` says when there is more of it.
   * Use one or the other, not both.
   */
  pageSize = 0,
  /** Debounce before a query function is called. */
  debounceMs = 200,
  /** Keep the top option armed on every change (TagInput's Enter-to-commit). */
  armTopOnChange = false,
  /** Optional `(item, query) => boolean`; defaults to label + value match. */
  matchTerm = null,
  /** Show nothing until something is typed (the GM panel's filter behaviour). */
  requireQuery = false,
  /**
   * Whether the highlight wraps past the ends and off the list entirely.
   * The tag field's convention (`-1 → 0…n-1 → -1`) lets a stray arrow cancel a
   * commit; a picker wants the highlight to stay put instead.
   */
  wrapHighlight = true,
}) {
  const listId = useId()
  const open = ref(false)
  const highlighted = ref(-1)
  const loading = ref(false)

  // ── source: a plain array, or a debounced query function ────────────────
  const isQuerySource = () => typeof options.value === 'function'
  const fetched = ref([])
  let seq = 0
  let timer = null

  async function runQuery(q) {
    const fn = options.value
    if (typeof fn !== 'function') return
    const mine = ++seq
    loading.value = true
    try {
      const list = await fn(q)
      if (mine !== seq) return          // a later query already answered
      fetched.value = Array.isArray(list) ? list : []
    } catch {
      if (mine !== seq) return
      fetched.value = []
    } finally {
      if (mine === seq) loading.value = false
    }
  }

  watch([() => options.value, query], ([src, q]) => {
    if (typeof src !== 'function') { clearTimeout(timer); return }
    clearTimeout(timer)
    timer = setTimeout(() => runQuery(q), debounceMs)
  })
  if (isQuerySource()) runQuery(query.value)

  onUnmounted(() => clearTimeout(timer))

  const source = computed(() => {
    const o = options.value
    if (typeof o === 'function') return fetched.value
    return Array.isArray(o) ? o : []
  })

  const normalized = computed(() => source.value.map(normalize))

  // The whole match set, before any window is applied.
  const matches = computed(() => {
    const q = query.value.trim().toLowerCase()
    if (requireQuery && !q) return []
    const taken = new Set([...(chosen.value ?? []), ...(exclude.value ?? [])])
    const hit = matchTerm || ((it, term) =>
      it.label.toLowerCase().includes(term) || String(it.value).toLowerCase().includes(term))
    // A query function is taken as authoritative: it matched server-side, and
    // re-filtering its results here would silently drop rows it deliberately
    // returned (a match on a field this list never sees).
    const serverMatched = typeof options.value === 'function'
    return normalized.value
      .filter((it) => !taken.has(it.value))
      .filter((it) => (serverMatched || !q ? true : hit(it, q)))
  })

  // How much of the match set is revealed. A new query — or a re-read of the
  // source — starts at one page again, or a long list would open already scrolled
  // deep into the previous one's results. Synchronous on purpose: the window has
  // to belong to the query it was typed for, not to the one before it, and a
  // deferred reset would render one frame of the old list against the new query.
  const shown = ref(pageSize)
  if (pageSize > 0) watch([query, source], () => { shown.value = pageSize }, { flush: 'sync' })

  const available = computed(() => {
    const list = matches.value
    if (pageSize > 0) return list.slice(0, shown.value)
    return maxResults > 0 ? list.slice(0, maxResults) : list
  })

  /** Whether the match set holds more than the window is showing. */
  const hasMore = computed(() => pageSize > 0 && matches.value.length > shown.value)

  /** Reveal one more page. A no-op once the whole match set is on screen. */
  function loadMore() {
    if (hasMore.value) shown.value += pageSize
  }

  const exactMatch = computed(() => {
    const q = query.value.trim().toLowerCase()
    if (!q) return false
    return normalized.value.some(
      (it) => String(it.value).toLowerCase() === q || it.label.toLowerCase() === q)
  })

  // The create row exists only when free text is allowed and is not already an
  // option — otherwise it would offer to create what the list already holds.
  const createText = computed(() => {
    const t = query.value.trim()
    return allowCustom && t && !exactMatch.value ? createLabel(t) : ''
  })

  const optionCount = computed(() => available.value.length + (createText.value ? 1 : 0))

  function armTop() { highlighted.value = optionCount.value ? 0 : -1 }

  /**
   * Walks -1 (nothing) → 0…count-1 → back to -1 when wrapping, so a highlight
   * can be cleared; otherwise it clamps at the ends.
   */
  function move(dir) {
    const count = optionCount.value
    if (!count) return
    open.value = true
    if (!wrapHighlight) {
      const next = Math.min(Math.max(highlighted.value + dir, 0), count - 1)
      // Stepping onto the last revealed row asks for the next page: the window is
      // a rendering decision, so a keyboard user has to be able to walk past it
      // rather than only reach the first page the scrollbar shows.
      if (dir > 0 && hasMore.value && next === count - 1) {
        loadMore()
        highlighted.value = Math.min(highlighted.value + dir, optionCount.value - 1)
        return
      }
      highlighted.value = next
      return
    }
    const max = count - 1
    if (dir > 0) highlighted.value = highlighted.value >= max ? -1 : highlighted.value + 1
    else highlighted.value = highlighted.value <= -1 ? max : highlighted.value - 1
  }

  /** The value free text should store, or null when it is not allowed. */
  function resolve(raw) {
    const v = String(raw ?? '').trim()
    if (!v) return null
    const byLabel = normalized.value.find((it) => it.label.toLowerCase() === v.toLowerCase())
    const byValue = normalized.value.find((it) => String(it.value) === v)
    if (!byLabel && !byValue) return allowCustom ? v : null
    return (byLabel ?? byValue).value
  }

  /** Presentation label for a stored value (falls back to the value itself). */
  function labelFor(value) {
    const it = normalized.value.find((s) => s.value === value)
    return it ? it.label : value
  }

  function openList() { open.value = true }
  function closeList() { open.value = false; highlighted.value = -1 }

  // Armed on the *match set*, not on the window: revealing another page must not
  // re-arm the highlight to the top (a keyboard user walking to the end of a page
  // would be thrown back to the first row of it). For an unpaged list the two are
  // the same list, so nothing changes for those shells.
  if (armTopOnChange) watch([query, matches], armTop)

  return {
    listId,
    open,
    loading,
    highlighted,
    available,
    hasMore,
    loadMore,
    exactMatch,
    createText,
    optionCount,
    activeDescendant: computed(() =>
      highlighted.value >= 0 ? `${listId}-opt-${highlighted.value}` : undefined),
    optionId: (i) => `${listId}-opt-${i}`,
    armTop,
    move,
    resolve,
    labelFor,
    openList,
    closeList,
  }
}
