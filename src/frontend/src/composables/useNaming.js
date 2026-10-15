import { ref } from 'vue'
import { useApi } from './useApi.js'

// Naming (B82). Two things every surface needs: the theme list for a picker, and a
// name for a world's theme.
//
// The theme list is fixed for a build, so it is fetched **once** and shared — three
// surfaces offer it (the universe picker in the entity form, the create panel and
// the sheet), and a round trip per mount would be three identical reads. A
// module-level ref rather than a promise, so a component that mounts after the first
// fetch still sees the loaded list instead of an empty dropdown.
const themes = ref([])
//: The theme a universe gets when it names none — read from the backend so the
//: picker's *Default* option is labelled with the real theme rather than a second
//: copy of the constant.
const defaultTheme = ref('')
let pending = null

export function useNaming() {
  const { graphql } = useApi()

  /** Every theme the backend declares, as `[{ key, label }]` — read, not hard-coded,
   *  so a theme added on the server appears in the dropdown with no frontend change. */
  async function loadThemes() {
    if (themes.value.length) return themes.value
    if (!pending) {
      pending = graphql('{ namingThemes { key label } namingDefaultTheme }')
        .then((data) => {
          themes.value = data?.namingThemes || []
          defaultTheme.value = data?.namingDefaultTheme || ''
          return themes.value
        })
        .finally(() => { pending = null })
    }
    return pending
  }

  /**
   * Names for a theme, or for the **universe's** theme when `theme` is omitted —
   * which is what the generate buttons want: the world decides how its people are
   * named, and the button should not have to know that.
   *
   * Returns `[]` rather than throwing. A name generator is a convenience on a form
   * the GM is filling in; a failed call must leave the form usable, and the local
   * generator on the server means the only failure mode is a dead network.
   */
  async function generateNames({ theme = '', universe = '', count = 1, gender = '' } = {}) {
    const data = await graphql(
      `query($theme: String!, $universe: String!, $count: Int!, $gender: String!) {
         randomNames(theme: $theme, universe: $universe, count: $count, gender: $gender)
       }`,
      { theme, universe, count, gender },
    )
    return data?.randomNames || []
  }

  async function generateName(options = {}) {
    return (await generateNames({ ...options, count: 1 }))[0] || ''
  }

  return { themes, defaultTheme, loadThemes, generateName, generateNames }
}
