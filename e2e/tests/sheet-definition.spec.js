import { test, expect } from '@playwright/test'

// Scanning sets for one with visible traits can take a few loads' worth of time.
test.setTimeout(120_000)
import { findPlayableCharacter, gql, openSheet, ensureTraitRowsVisible, openTraitEditor } from '../helpers/sheet.js'

// The trait editor's "Definition" control — changing an instance's registry trait.
//
// This exists because the control shipped broken in a way no static check could
// see and no probe of mine caught: the picker's open state lived inside
// `TraitEditPanel`, which the sheet re-creates whenever it re-renders. The first
// click set it open, the options arrived, the re-render replaced the panel, and
// the fresh instance had it closed again — so the list only ever appeared on a
// *second* click, once the fetch was cached. A user clicks once.
//
// Hence the shape of the assertion below: one click, then look.

/**
 * Open the definition picker with a single click, and wait for its options.
 *
 * Both halves matter. One click is the regression assertion — the panel used to
 * wipe its own open state on the re-render that follows the fetch, so the list
 * only appeared on a second click. And the wait is for the *options*, not the
 * box: the dropdown is visible the instant the chip is clicked, while the options
 * are fetched on open and land a beat later. Every count in this file counts
 * options, so reading too early reports zero — which reads exactly like "the
 * picker is broken" and is not.
 */
async function openDefinitionPicker(page) {
  await page.locator('.definition-chip').click()
  await expect(page.locator('.definition-dropdown'), 'one click must open the picker').toBeVisible()
  await expect(page.locator('.definition-option').first(), 'the picker must load its options')
    .toBeVisible({ timeout: 10_000 })
}

test('the definition picker opens on the first click', async ({ page, request }) => {
  const character = await findPlayableCharacter(request)
  await openSheet(page, character)
  await ensureTraitRowsVisible(page)
  await openTraitEditor(page)

  const chip = page.locator('.definition-chip')
  await expect(chip).toBeVisible()
  const current = (await chip.innerText()).trim()
  expect(current.length, 'the chip names the instance’s current definition').toBeGreaterThan(0)

  await openDefinitionPicker(page)
  expect(await page.locator('.definition-option').count(), 'the picker must offer candidates')
    .toBeGreaterThan(0)

  // The current definition is always among them, marked as selected, so the list
  // is never a dead end and the player can see where they are.
  await expect(page.locator('.definition-option.selected')).toHaveText(new RegExp(current, 'i'))
})

test('the traitset filter opens on the instance’s own set, and can widen', async ({ page, request }) => {
  const character = await findPlayableCharacter(request)
  await openSheet(page, character)
  await ensureTraitRowsVisible(page)
  const settingId = await openTraitEditor(page)
  const setting = character.traitSettings.find((s) => s.id === settingId)
  expect(setting, `the edited setting ${settingId} is in the fetched list`).toBeTruthy()

  await openDefinitionPicker(page)
  const setFilter = page.locator('.definition-set-filter')
  await expect(setFilter, 'the picker offers a trait set filter').toBeVisible()

  // The default is the set the instance already lives in — not "all", and not the
  // first set in the list by accident.
  await expect(setFilter).toHaveValue(setting.traitsetId)
  const inSet = await page.locator('.definition-option').count()
  expect(inSet, 'the instance’s own set must offer at least its current definition').toBeGreaterThan(0)

  // Widening to every set can only add candidates, never remove one. `selectOption('')`
  // is the "All trait sets" option.
  await setFilter.selectOption('')
  await expect
    .poll(async () => page.locator('.definition-option').count(), { timeout: 5_000 })
    .toBeGreaterThanOrEqual(inSet)

  // Narrowing back restores exactly the set's candidates.
  await setFilter.selectOption(setting.traitsetId)
  await expect
    .poll(async () => page.locator('.definition-option').count(), { timeout: 5_000 })
    .toBe(inSet)
})

test('the definitions are listed alphabetically', async ({ page, request }) => {
  const character = await findPlayableCharacter(request)
  await openSheet(page, character)
  await ensureTraitRowsVisible(page)
  await openTraitEditor(page)

  await openDefinitionPicker(page)
  // Every set, not just the instance's: a single set can happen to come back
  // alphabetical from the API, which lets an unsorted list pass by luck. Across
  // the whole universe that is not a coincidence that can survive.
  await page.locator('.definition-set-filter').selectOption('')
  const labels = await page.locator('.definition-option').evaluateAll(
    (els) => els.map((e) => e.innerText.trim()),
  )
  expect(labels.length, 'the list must have something to order').toBeGreaterThan(50)

  // Non-decreasing, checked pairwise rather than against a re-sorted copy: a
  // sorted copy would just re-run the implementation and pass whatever it did.
  // Case-insensitively, because that is how the list reads.
  for (let i = 1; i < labels.length; i++) {
    const order = labels[i - 1].localeCompare(labels[i], undefined, { sensitivity: 'base' })
    expect(
      order,
      `"${labels[i - 1]}" comes before "${labels[i]}" but sorts after it (position ${i})`,
    ).toBeLessThanOrEqual(0)
  }
})

test('the picker filters, and closing it leaves the editor open', async ({ page, request }) => {
  const character = await findPlayableCharacter(request)
  await openSheet(page, character)
  await ensureTraitRowsVisible(page)
  await openTraitEditor(page)

  const chip = page.locator('.definition-chip')
  await openDefinitionPicker(page)
  const filter = page.locator('.definition-filter')
  await expect(filter).toBeVisible()

  const all = await page.locator('.definition-option').count()
  await filter.fill('e')
  await expect
    .poll(async () => page.locator('.definition-option').count(), { timeout: 5_000 })
    .toBeLessThan(all)

  // Closing is a toggle, and it must not disturb the editor it sits in — the
  // draft fields the player was editing are the panel's, and re-opening them
  // from scratch would silently discard their work.
  await chip.click()
  await expect(page.locator('.definition-dropdown')).toBeHidden()
  await expect(page.locator('.trait-edit-panel')).toBeVisible()
  await expect(chip).toHaveText(new RegExp((await chip.innerText()).trim(), 'i'))
})

test('the sheet reports no console or page errors while the picker is used', async ({ page, request }) => {
  // This session has already shipped a silent no-op to the human's console once,
  // and a control that throws on click looks identical to one that does nothing.
  //
  // Scoped on purpose: uncaught exceptions always count, but console output only
  // counts when it comes from the sheet. The app also logs *caught*, unrelated
  // network failures through `console.error` (a Firefox `fetchSfxCatalog`
  // NetworkError reproduces here regularly), and failing on those would make this
  // test flaky for reasons that have nothing to do with the picker.
  const pageErrors = []
  const sheetErrors = []
  page.on('pageerror', (e) => pageErrors.push(String(e)))
  page.on('console', (m) => {
    if (m.type() !== 'error') return
    const text = m.text()
    if (/\[sheet\]|definition/i.test(text)) sheetErrors.push(text)
  })

  const character = await findPlayableCharacter(request)
  await openSheet(page, character)
  await ensureTraitRowsVisible(page)
  await openTraitEditor(page)

  const chip = page.locator('.definition-chip')
  await openDefinitionPicker(page)
  await chip.click()
  await expect(page.locator('.definition-dropdown')).toBeHidden()

  expect(pageErrors, `uncaught page errors: ${pageErrors.join(' | ')}`).toEqual([])
  expect(sheetErrors, `sheet errors: ${sheetErrors.join(' | ')}`).toEqual([])
})

// ── The relationship step (relations traitset) ───────────────────

const escapeRe = (s) => String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/**
 * Open the add-trait picker and choose the `relations` set.
 *
 * When the sheet is drilled into a set, the picker opens straight on *that* set's
 * traits (by design — the set you are looking at is the set you are adding to), so
 * reach the list through Back when it is not already showing.
 */
async function openRelationsStep(page) {
  await page.getByRole('button', { name: /Add Trait/i }).click()
  const relations = page.locator('.trait-picker .picker-item')
    .filter({ hasText: /^relations$/i })
  if (!(await relations.count())) await page.locator('.picker-back').first().click()
  await relations.first().click()
  await expect(page.locator('.picker-filter'), 'picking relations must ask which relationship')
    .toBeVisible()
}

const pickerItem = (page, label) => page.locator('.trait-picker .picker-item')
  .filter({ hasText: new RegExp(`^${escapeRe(label)}\\b`, 'i') })

test('adding from the relations set asks which relationship first', async ({ page, request }) => {
  const character = await findPlayableCharacter(request)
  await openSheet(page, character)
  await ensureTraitRowsVisible(page)

  await openRelationsStep(page)
  await expect(page.locator('.trait-picker h4')).toHaveText(/which relationship/i)

  // The contacts are fetched on entering the step, so wait for them: the filter
  // and the heading are there before the list is.
  await expect(page.locator('.trait-picker .picker-item').first(), 'the contacts must load')
    .toBeVisible({ timeout: 15_000 })

  // Each contact carries its type, so a place or a faction reads as what it is.
  const listed = await page.locator('.trait-picker .picker-item').evaluateAll(
    (els) => els.map((e) => e.innerText.replace(/\s+/g, ' ').trim()),
  )
  expect(listed.length, 'a character carrying relations traits should have contacts')
    .toBeGreaterThan(0)
  expect(listed.every((t) => /\S/.test(t)), 'every contact is named').toBe(true)

  // The extra step is *only* for this set. An ordinary set must go straight to its
  // traits, or every add would cost a click more than it used to.
  await page.locator('.picker-back').click()
  await page.locator('.trait-picker .picker-item')
    .filter({ hasText: /^assets$/i }).first().click()
  await expect(page.locator('.picker-filter'), 'an ordinary set must not ask for a relationship')
    .toHaveCount(0)
})

test('a relationship trait on one contact is still offered for another', async ({ page, request }) => {
  // A relationship trait's id is `{edge}:{trait}`, so the same definition belongs
  // on two contacts. The picker filtered "already assigned" entity-wide, which
  // hid four of the relations set's twenty-four traits from *every* contact
  // because they sat on one.
  const character = await findPlayableCharacter(request)
  const relations = character.traitSettings.filter((s) =>
    s.fromType === 'relationship' && s.relationshipType === 'relation' && s.relationshipContactId)
  expect(relations.length, 'this test needs contacts carrying relationship traits')
    .toBeGreaterThan(1)
  const first = relations[0]
  const other = relations.find((s) => s.relationshipContactId !== first.relationshipContactId)
  expect(other, 'this test needs two *different* contacts carrying traits').toBeTruthy()

  const nameOf = async (id) =>
    (await gql(request, `query($id: ID!) { entity(id: $id) { name } }`, { id })).entity.name
  const holder = await nameOf(first.relationshipContactId)
  const target = await nameOf(other.relationshipContactId)

  await openSheet(page, character)
  await ensureTraitRowsVisible(page)
  await openRelationsStep(page)

  // On the contact that already has it: not offered again.
  await pickerItem(page, holder).first().click()
  await expect(pickerItem(page, first.name), `${first.name} is already on ${holder}`)
    .toHaveCount(0)

  // On a different contact: still offered, which is the point.
  await page.locator('.picker-back').click()
  await pickerItem(page, target).first().click()
  await expect(pickerItem(page, first.name), `${first.name} must be offerable for ${target}`)
    .toHaveCount(1)
})
