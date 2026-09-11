import { watch } from 'vue'
import { useColorMode, usePreferredDark } from '@vueuse/core'

/**
 * Light/dark theme: follows the OS by default, with a manual override persisted
 * under `transversal-color-scheme`. `useColorMode` writes `.dark`/`.light` on
 * `<html>`; the stylesheet defaults to dark and `html.light` overrides it.
 *
 * `emitAuto` keeps the *preference* visible ('auto' | 'light' | 'dark') instead
 * of collapsing it to the resolved theme — the settings control has an Auto
 * segment, and without this it would jump to Light/Dark the moment you picked
 * it. The `theme-color` meta follows the theme actually applied, so in auto it
 * tracks the device preference.
 */
export function useThemeMode() {
  const prefersDark = usePreferredDark()
  const colorMode = useColorMode({
    selector: 'html',
    storageKey: 'transversal-color-scheme',
    emitAuto: true,
  })

  watch([colorMode, prefersDark], ([mode, dark]) => {
    const isLight = mode === 'auto' ? !dark : mode === 'light'
    const meta = document.querySelector('meta[name="theme-color"]')
    if (meta) meta.setAttribute('content', isLight ? '#e9e9ee' : '#0a0a0f')
  }, { immediate: true })

  return { colorMode }
}
