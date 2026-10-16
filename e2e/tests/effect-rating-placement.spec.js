import { test, expect } from '@playwright/test'

// The **rating** an effect asks for is one control, and a trait-creating verb
// renders it *inside* the trait instance editor — beside the rating type it
// belongs with — rather than in a field of its own below the box ([[B307]]).
//
// Why this is a browser test and not a grep: the rating spent a day in the field
// instead, and the answer to "where did the rating go" was a screenshot nobody had
// taken. The seam is the shared editor's `after-dice` slot opening only under some
// props, and a `v-bind` of `onUpdate:*` handlers — neither of which a static check
// can see, and both of which fail silently (a mode button that does not change the
// mode saves the wrong thing).
//
// This renders the real components through the dev server's own module graph, so
// the scoped CSS is the CSS under test. Against a built bundle the modules cannot
// be imported and the test skips rather than lying.

async function mountRating() {
  // The app already loaded Vue, so take the URL Vite served it from rather than
  // guessing the optimizer's hashed path.
  const vueUrl = performance.getEntriesByType('resource').map((e) => e.name)
    .find((u) => /\/deps\/vue\.js/.test(u))
  if (!vueUrl) throw new Error('no vite vue dep in the resource timeline')
  const vue = await import(/* @vite-ignore */ vueUrl)
  const Editor = (await import(/* @vite-ignore */ '/src/components/ui/TraitInstanceEditor.vue')).default
  const Control = (await import(/* @vite-ignore */ '/src/components/gm/EffectRatingControl.vue')).default

  const state = vue.reactive({ mode: 'die', row: ['d6', 'd6'], result: 'd6' })
  const host = document.createElement('div')
  host.id = 'rating-probe'
  document.body.appendChild(host)

  const mount = (controlProps, editorProps = {}) => {
    const el = document.createElement('div')
    host.appendChild(el)
    vue.createApp({
      render: () => vue.h(Editor, {
        // Exactly what EffectForm passes for a gain verb: the editor's own dice
        // row is off, because the rating is rendered in the slot instead.
        mode: 'single', variant: 'box', showDice: false, showCapacity: false,
        showPolarity: true, showStatement: true, showNotes: true,
        ratingType: 'STATIC', polarity: 'POSITIVE',
        ...editorProps,
      }, {
        'after-dice': () => vue.h(Control, {
          field: { options: ['d4', 'd6', 'd8'] },
          variables: ['effect_die'],
          canRow: true,
          ...controlProps,
          mode: state.mode,
          row: state.row,
          result: state.result,
          'onUpdate:mode': (m) => { state.mode = m },
          'onUpdate:row': (r) => { state.row = r },
          'onUpdate:result': (v) => { state.result = v },
        }),
      }),
    }).mount(el)
    return el
  }

  const rowHost = mount({})
  const singleHost = mount({ canRow: false })

  // Snapshot the resting state *before* driving the modes: the two hosts share
  // one reactive mode, so reading them after a click reads the new mode.
  const resting = {
    canRowDice: rowHost.querySelectorAll('.die-picker.multiple').length,
    canRowDicePicker: singleHost.querySelectorAll('.die-picker.multiple').length,
    dieOptions: [...singleHost.querySelectorAll('.ee-rating select option')].map((o) => o.value),
  }

  rowHost.querySelectorAll('.ee-result-mode button')[1].click()   // "Variable"
  await new Promise((r) => setTimeout(r, 0))
  const afterVariable = {
    mode: state.mode,
    active: [...rowHost.querySelectorAll('.ee-result-mode button')]
      .map((b) => (b.classList.contains('active') ? b.textContent.trim() : null)).filter(Boolean),
    options: [...rowHost.querySelectorAll('select option')].map((o) => o.value),
    labels: [...rowHost.querySelectorAll('select option')].map((o) => o.textContent.trim()),
  }
  rowHost.querySelectorAll('.ee-result-mode button')[2].click()   // "Path"
  await new Promise((r) => setTimeout(r, 0))
  const afterPath = {
    mode: state.mode,
    hasPathField: !!rowHost.querySelector('.ee-rating .pf-root'),
  }

  return {
    insideEditor: !!rowHost.querySelector('.trait-instance-editor .ee-rating'),
    modeLabels: [...rowHost.querySelectorAll('.ee-result-mode button')].map((b) => b.textContent.trim()),
    editorHasOwnDice: !!rowHost.querySelector('.trait-instance-editor .te-dice'),
    ...resting,
    afterVariable,
    afterPath,
  }
}

test('a gain verb\'s rating renders inside the trait instance editor, with all three modes', async ({ page }) => {
  await page.goto('/')
  await page.waitForLoadState('domcontentloaded')

  let m
  try {
    m = await page.evaluate(mountRating)
  } catch (e) {
    test.skip(true, `needs a Vite dev server to render the SFC: ${e.message}`)
  }

  // Inside the box, and the box no longer draws a die of its own — one control.
  expect(m.insideEditor, 'the rating must render inside .trait-instance-editor').toBe(true)
  expect(m.editorHasOwnDice, 'the editor must not draw a second die control').toBe(false)
  expect(m.modeLabels).toEqual(['Dice', 'Variable', 'Path'])

  // A row where the action declares one, a plain dropdown where it does not.
  expect(m.canRowDice, 'a whole-rating action gets the dice row').toBe(1)
  expect(m.canRowDicePicker, 'a single-die action must not get a row').toBe(0)
  expect(m.dieOptions).toEqual(['d4', 'd6', 'd8'])

  // The emit wiring: clicking a mode changes the mode the host saves, and the
  // control re-renders to match. A `v-bind` of `onUpdate:*` that did not fire
  // would leave this at 'die' while the button looked active.
  expect(m.afterVariable.mode).toBe('variable')
  expect(m.afterVariable.active).toEqual(['Variable'])
  expect(m.afterVariable.labels).toContain('— variable —')
  expect(m.afterVariable.options).toContain('{effect_die}')
  expect(m.afterPath.mode).toBe('spec')
  expect(m.afterPath.hasPathField, 'the Path mode must actually render a path builder').toBe(true)
})
