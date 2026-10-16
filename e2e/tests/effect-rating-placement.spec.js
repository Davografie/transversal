import { test, expect } from '@playwright/test'

// The **rating** an effect asks for is one control, and a trait-creating verb
// renders it *inside* the trait instance editor — beside the rating type it
// belongs with — rather than in a field of its own below the box ([[B307]]).
//
// Why this is a browser test and not a grep: three UI mistakes were shipped on
// this ticket by reading the template and reasoning.
//
//   1. `visibleFields` hid the rating field on a gain verb, so the Path mode was
//      **unreachable** — a claim that it was visible was wrong when it was made.
//   2. The rating was moved out of the editor into the field, and the answer to
//      "where did the rating go" was the author's report.
//   3. `ratingControl` read `sourceElement` and `outputVariables` as bare
//      identifiers, which in `<script setup>` are **not** prop bindings: the
//      computed threw a `ReferenceError` and the panel went blank. The build was
//      green, every static check passed, and mounting the *child* pair directly —
//      which is what the first version of this spec did — could not see it.
//
// So this mounts the **real `EffectForm`**, so its own bindings are exercised,
// and it fails on any error the component reports while rendering.
//
// It drives the form through a synthetic action list rather than the API, so it
// needs no session and no live content — the actions are the shapes under test,
// not the world.
//
// This renders the real components through the dev server's own module graph, so
// the scoped CSS is the CSS under test. Against a built bundle the modules cannot
// be imported and the test skips rather than lying.

// The action shapes live **inside** `driveForm`, not beside it: `page.evaluate`
// serializes that one function, so a module-scope constant would be an undefined
// identifier in the browser.
async function driveForm() {
  /** A gain verb: creates a trait, and declares a whole rating (`dice`). */
  const GAIN = {
    actionId: 'gain_trait', label: 'Gain Trait', group: 'Traits',
    effectType: 'modify_trait', effectAction: 'gain',
    validTimings: ['IMMEDIATE'], supportsPolarity: true, outputElement: 'traitsetting',
    fields: [
      { name: 'target', label: 'Trait', fieldType: 'text', required: true, hiddenWhenRef: 'trait', options: [] },
      { name: 'result', label: 'Die Rating', fieldType: 'die_select', required: true, options: ['d4', 'd6', 'd8', 'd10', 'd12'] },
    ],
    contextFields: [
      { name: 'statement', label: 'Statement', fieldType: 'text', options: [] },
      { name: 'notes', label: 'Notes', fieldType: 'text', options: [] },
      { name: 'dice', label: 'Rating dice', fieldType: 'dice_array', options: [] },
    ],
    refs: [{ name: 'trait', label: 'Trait', elements: ['trait'] }],
  }

  /** A single-die verb: the same `result` field, no rating row. */
  const ADD_DIE = {
    actionId: 'add_rating_die', label: 'Add Rating Die', group: 'Traits',
    effectType: 'modify_trait', effectAction: 'add_die',
    validTimings: ['IMMEDIATE'], supportsPolarity: false,
    fields: [
      { name: 'target', label: 'Trait', fieldType: 'text', required: true, options: [] },
      { name: 'result', label: 'Die', fieldType: 'die_select', required: true, options: ['d4', 'd6', 'd8', 'd10', 'd12'] },
    ],
    contextFields: [],
    refs: [],
  }

  // The app already loaded Vue, so take the URL Vite served it from rather than
  // guessing the optimizer's hashed path.
  const vueUrl = performance.getEntriesByType('resource').map((e) => e.name)
    .find((u) => /\/deps\/vue\.js/.test(u))
  if (!vueUrl) throw new Error('no vite vue dep in the resource timeline')
  const vue = await import(/* @vite-ignore */ vueUrl)
  const { useEffectActions } = await import(/* @vite-ignore */ '/src/composables/useEffectActions.js')
  const { actions } = useEffectActions()
  actions.value = [GAIN, ADD_DIE]
  const EffectForm = (await import(/* @vite-ignore */ '/src/components/gm/EffectForm.vue')).default

  const tick = () => new Promise((r) => setTimeout(r, 0))
  const errors = []
  const host = document.createElement('div')
  host.id = 'effect-form-probe'
  document.body.appendChild(host)

  const mount = async (actionId, formProps = {}) => {
    const el = document.createElement('div')
    host.appendChild(el)
    const app = vue.createApp({ render: () => vue.h(EffectForm, { value: null, ...formProps }) })
    // A render error is otherwise swallowed into the console and the panel is
    // simply blank — which is exactly how the ReferenceError shipped.
    app.config.errorHandler = (err) => errors.push(String((err && err.message) || err))
    app.mount(el)
    await tick()
    const select = el.querySelector('.ee-form > select')
    select.value = actionId
    select.dispatchEvent(new Event('change'))
    await tick()
    await tick()
    return el
  }

  const gain = await mount('gain_trait')
  // One die-typed name in scope — the case "Variable" exists for. Without it the
  // mode has nothing to offer and is not offered at all: a rating die is a *list*,
  // so "the rating the source already has" is never a single named die.
  const withVar = await mount('gain_trait', { variables: [{ name: 'effect_die', type: 'die' }] })
  const single = await mount('add_rating_die')

  const rating = gain.querySelector('.trait-instance-editor .ee-rating')
  const varRating = withVar.querySelector('.trait-instance-editor .ee-rating')
  const resting = {
    insideEditor: !!rating,
    editorDice: gain.querySelectorAll('.trait-instance-editor .te-dice').length,
    modeLabels: rating ? [...rating.querySelectorAll('.ee-result-mode button')].map((b) => b.textContent.trim()) : [],
    diceRow: rating ? rating.querySelectorAll('.die-picker.multiple').length : 0,
    fieldsOutside: gain.querySelectorAll('.ee-field > .ee-rating').length,
  }

  // Where the mode *is* offered: clicking it must actually select it.
  const variableBtn = varRating
    ? [...varRating.querySelectorAll('.ee-result-mode button')].find((b) => b.textContent.trim() === 'Variable')
    : null
  const variableOffered = !!variableBtn
  if (variableBtn) { variableBtn.click(); await tick(); await tick() }
  const afterVariable = {
    active: varRating ? [...varRating.querySelectorAll('.ee-result-mode button')]
      .map((b) => (b.classList.contains('active') ? b.textContent.trim() : null)).filter(Boolean) : [],
    labels: varRating ? [...varRating.querySelectorAll('select option')].map((o) => o.textContent.trim()) : [],
  }

  return {
    errors,
    ...resting,
    variableOffered,
    afterVariable,
    singleDiceRow: single.querySelectorAll('.die-picker.multiple').length,
    singleOptions: [...single.querySelectorAll('.ee-rating select option')].map((o) => o.value),
  }
}

test('a gain verb\'s rating is one control, inside the trait instance editor', async ({ page }) => {
  await page.goto('/')
  await page.waitForLoadState('domcontentloaded')

  let m
  try {
    m = await page.evaluate(driveForm)
  } catch (e) {
    test.skip(true, `needs a Vite dev server to render the SFC: ${e.message}`)
  }

  // The one that shipped: no render error at all.
  expect(m.errors, 'the form must render without an error').toEqual([])

  // Inside the box, and the box draws no die of its own — exactly one control.
  expect(m.insideEditor, 'the rating must render inside .trait-instance-editor').toBe(true)
  expect(m.editorDice, 'the editor must not draw a second die control').toBe(0)
  expect(m.fieldsOutside, 'the rating field must not also render its own control').toBe(0)
  // Nothing to name, so the mode that names one die is not offered — an option
  // that opens on an empty list is a dead end.
  expect(m.modeLabels).toEqual(['Dice', 'Path'])

  // A whole-rating action gets the row; a single-die action gets the dropdown.
  expect(m.diceRow, 'a whole-rating action gets the dice row').toBe(1)
  expect(m.singleDiceRow, 'a single-die action must not get a row').toBe(0)
  expect(m.singleOptions).toEqual(['d4', 'd6', 'd8', 'd10', 'd12'])

  // And where there *is* a die-typed name, the mode appears and the wiring works:
  // a `v-bind` of `onUpdate:*` that did not fire would leave the button looking
  // active while the host still saved `die`.
  expect(m.variableOffered, 'a die-typed name in scope must offer the Variable mode').toBe(true)
  expect(m.afterVariable.active).toEqual(['Variable'])
  expect(m.afterVariable.labels).toContain('— variable —')
  expect(m.afterVariable.labels).toContain('{effect_die}')
})
