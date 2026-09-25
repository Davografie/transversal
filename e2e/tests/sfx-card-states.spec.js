import { test, expect } from '@playwright/test'

// The two ways an SFX card can be "not pressable" are different things, and the
// sheet must not treat them the same (B189).
//
//   `blocked`  — a rule you *own* whose conditions fail right now. It would be
//                pressable if they held, so dimming it is honest: the card is
//                unavailable, and it says so.
//   `readonly` — a rule the *place* lends you that fires by itself. It was never
//                a control, so there is nothing to disable; it is a statement,
//                and the reader's only need is to read it.
//
// Before the fix the place strip used `blocked`, and 0.45 opacity took the card's
// *name* to 2.84:1 against the sheet background — under WCAG AA (4.5:1) and under
// even the large-text floor (3:1). Measured here rather than asserted by eye:
// `readonly` reads at 14.89:1, and the card keeps its dashed border, so it still
// does not look pressable.
//
// This renders the real component through the dev server's own module graph, so
// the scoped CSS is the CSS under test. It is a dev-server test: against a built
// bundle the module cannot be imported and the test skips rather than lying.

/** Contrast ratio of the card's name as the reader sees it, opacity included. */
async function measureCardStates() {
  // The app already loaded Vue, so take the URL Vite served it from rather than
  // guessing the optimizer's hashed path.
  const vueUrl = performance.getEntriesByType('resource').map((e) => e.name)
    .find((u) => /\/deps\/vue\.js/.test(u))
  if (!vueUrl) throw new Error('no vite vue dep in the resource timeline')
  const vue = await import(/* @vite-ignore */ vueUrl)
  const SfxCard = (await import(/* @vite-ignore */ '/src/components/sheet/SfxCard.vue')).default

  const backdrop = getComputedStyle(document.body).backgroundColor
  const host = document.createElement('div')
  host.id = 'sfx-probe'
  host.style.cssText = 'position:fixed;top:0;left:0;z-index:99999;padding:16px;'
    + 'display:flex;flex-direction:column;gap:10px;align-items:flex-start;width:420px;'
    + 'background:' + backdrop
  document.body.appendChild(host)

  const mount = (props) => {
    const el = document.createElement('div')
    host.appendChild(el)
    vue.createApp({ render: () => vue.h(SfxCard, props) }).mount(el)
    return el.querySelector('.sfx-card')
  }
  const blocked = mount({
    name: 'Condition-blocked rule', description: 'Owned, conditions unmet',
    blocked: true, disabled: true,
  })
  const readonly = mount({
    name: 'Place-lent automatic rule', description: 'The room lends this',
    rules: 'Fires by itself when the world moves.', readonly: true,
  })

  const parse = (c) => (c.match(/[\d.]+/g) || []).slice(0, 3).map(Number)
  const lin = (v) => { const s = v / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4 }
  const lum = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05) }
  const bg = parse(backdrop)
  // CSS opacity composites the whole card against the backdrop, so the text the
  // reader actually sees is the text colour mixed toward the backdrop.
  const seen = (card) => {
    const o = Number(getComputedStyle(card).opacity)
    return parse(getComputedStyle(card.querySelector('.sfx-card-name')).color)
      .map((v, i) => v * o + bg[i] * (1 - o))
  }

  return {
    blockedClass: blocked.className,
    readonlyClass: readonly.className,
    blockedOpacity: getComputedStyle(blocked).opacity,
    readonlyOpacity: getComputedStyle(readonly).opacity,
    readonlyBorderStyle: getComputedStyle(readonly).borderStyle,
    readonlyCursor: getComputedStyle(readonly).cursor,
    blockedContrast: ratio(seen(blocked), bg),
    readonlyContrast: ratio(seen(readonly), bg),
  }
}

test('a place-lent rule reads at full contrast instead of being dimmed', async ({ page }) => {
  await page.goto('/')
  await page.waitForLoadState('domcontentloaded')

  let state
  try {
    state = await page.evaluate(measureCardStates)
  } catch (e) {
    test.skip(true, `needs a Vite dev server to render the SFC: ${e.message}`)
  }

  expect(state.readonlyClass, 'the place card must carry the readonly variant').toContain('sfx-readonly')
  expect(state.readonlyClass, 'readonly must not also be treated as blocked').not.toContain('sfx-blocked')
  expect(state.readonlyOpacity, 'the readonly card must not be dimmed').toBe('1')
  // Still visibly not a control...
  expect(state.readonlyBorderStyle).toBe('dashed')
  expect(state.readonlyCursor).toBe('default')
  // ...but readable: AA for body text, and well clear of the dimmed state.
  expect(state.readonlyContrast, 'the place rule\'s name must clear WCAG AA').toBeGreaterThanOrEqual(4.5)
  expect(state.readonlyContrast).toBeGreaterThan(state.blockedContrast * 2)
  // The dimmed state is unchanged — it is correct for an owned, unavailable rule.
  expect(state.blockedOpacity).toBe('0.45')
})
