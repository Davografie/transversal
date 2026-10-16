import { ref, watch } from 'vue'

/**
 * "Find character" + "New character" in the settings overlay: the debounced
 * search across all CHARACTER entities (excluding the ones you already own),
 * the skeleton/empty states, and creating a character (which claims it).
 *
 * `onChoose` is how picking a found character starts the perspective switch —
 * that machinery stays in the app.
 */
export function useCharacterFinder({
  playerId,
  playerEntities,
  fetchPlayerEntities,
  fetchLocationNames,
  onChoose = () => {},
}) {
  // Find character
  const charSearch = ref('')
  const charSearchResults = ref([])
  const charSearching = ref(false)
  const charSearchSearched = ref(false)
  const charSearchError = ref('')
  let charSearchDebounce = null
  let allCharactersCache = null

  // New character
  const newCharName = ref('')
  const creatingChar = ref(false)
  const createCharError = ref('')
  const showNewChar = ref(false)
  /**
   * The character this client just created, if any ([[B303]]).
   *
   * It is the one fact that tells a `client/life_path` action which surface to
   * use: a character created *here* is shown its path in the overlay the player
   * is already in, and a character that arrived some other way is shown it in its
   * own sheet. The server cannot tell the difference, so the client keeps it.
   */
  const lastCreatedId = ref('')

  async function fetchAllCharacters() {
    if (allCharactersCache) return allCharactersCache
    fetchLocationNames()
    const r = await fetch('/api/v1/graphql', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: `query { entities(type: CHARACTER) { id name type sheetPortrait currentLocation currentUniverse } }` })
    })
    const json = await r.json()
    allCharactersCache = json.data?.entities || []
    return allCharactersCache
  }

  function onCharSearchEnter() {
    if (charSearchDebounce) clearTimeout(charSearchDebounce)
    doCharSearch()
  }

  // Watch charSearch for live suggestions in settings panel
  watch(charSearch, (val) => {
    charSearchError.value = ''
    charSearchSearched.value = false
    if (charSearchDebounce) clearTimeout(charSearchDebounce)
    const q = val.trim()
    if (!q) {
      charSearchResults.value = []
      return
    }
    charSearchDebounce = setTimeout(() => { doCharSearch() }, 200)
  })

  async function doCharSearch() {
    const q = charSearch.value.trim()
    if (!q) {
      charSearchResults.value = []
      charSearchSearched.value = false
      return
    }
    charSearching.value = true
    charSearchError.value = ''
    try {
      const all = await fetchAllCharacters()
      const owned = new Set(playerEntities.value.map(e => e.id))
      charSearchResults.value = all
        .filter(e => String(e.name || '').toLowerCase().includes(q.toLowerCase()))
        .filter(e => !owned.has(e.id))
        .slice(0, 20)
    } catch (e) {
      charSearchError.value = e.message
      charSearchResults.value = []
    } finally {
      charSearching.value = false
      charSearchSearched.value = true
    }
  }

  function chooseFoundCharacter(e) {
    charSearch.value = ''
    charSearchResults.value = []
    charSearchSearched.value = false
    charSearchError.value = ''
    onChoose(e)
  }

  async function createCharacter() {
    const name = newCharName.value.trim()
    if (!name || creatingChar.value) return
    creatingChar.value = true
    createCharError.value = ''
    try {
      const r = await fetch('/api/v1/graphql', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: `mutation($input: CreateEntityInput!) { createEntity(input: $input) { id name type } }`,
          variables: { input: { name, type: 'CHARACTER', universe: 'earth' } }
        })
      })
      const json = await r.json()
      const eid = json.data?.createEntity?.id
      if (eid) {
        await fetch(`/api/v1/players/${playerId.value}/claim/${eid}`, { method: 'POST' })
        // Set before the switch below, so an intro that lands during it is judged
        // as "created here" rather than as a path for a character we merely play.
        lastCreatedId.value = eid
        newCharName.value = ''
        showNewChar.value = false
        allCharactersCache = null
        fetchPlayerEntities()
        // **Auto-activate** (the author, 2026-10-16). Creating a character used to
        // leave you as whoever you already were, looking at a new name in a list —
        // and a rule that fired *for* that character had nowhere to land. Switching
        // puts you in it, which is what makes the reveal mean anything, and it is
        // the same path the character chips already take.
        onChoose({ id: eid, name: json.data?.createEntity?.name || '', type: 'CHARACTER' })
      } else {
        createCharError.value = 'Failed to create character'
      }
    } catch (e) {
      createCharError.value = e.message
    } finally {
      creatingChar.value = false
    }
  }

  /** Clear the finder/creator state (the overlay reopens fresh). */
  function resetFinder() {
    newCharName.value = ''
    createCharError.value = ''
    showNewChar.value = false
    charSearch.value = ''
    charSearchResults.value = []
    charSearching.value = false
    charSearchSearched.value = false
    charSearchError.value = ''
  }

  return {
    charSearch, charSearchResults, charSearching, charSearchSearched, charSearchError,
    newCharName, creatingChar, createCharError, showNewChar, lastCreatedId,
    fetchAllCharacters, onCharSearchEnter, doCharSearch, chooseFoundCharacter,
    createCharacter, resetFinder,
  }
}
