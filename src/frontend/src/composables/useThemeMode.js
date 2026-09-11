import { watch } from 'vue'
import { useColorMode } from '@vueuse/core'

/**
 * Light/dark theme: follows the OS by default, with a manual override persisted
 * under `transversal-color-scheme`. `useColorMode` writes `.dark`/`.light` on
 * `<html>`; the stylesheet defaults to dark and `html.light` overrides it.
 *
 * The `theme-color` meta is kept in step so the mobile browser chrome matches
 * the app background instead of flashing the wrong shade.
 */
export function useThemeMode() {
  const colorMode = useColorMode({ selector: 'html', storageKey: 'transversal-color-scheme' })

  watch(colorMode, (m) => {
    const meta = document.querySelector('meta[name="theme-color"]')
    if (meta) meta.setAttribute('content', m === 'light' ? '#e9e9ee' : '#0a0a0f')
  }, { immediate: true })

  return { colorMode }
}
