import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { asPlayer } from '../helpers/role.js'
import { establishSession } from '../helpers/session.js'

// A rule that is **granted** by another rule's reach is available and must be
// *drawn* ([[Dynamic SFX Reach]]). A granted rule attaches nothing, so the
// attached lists (`sfxIds`) can never show one — `availableSfxIds` only answers
// yes/no about a card already listed.
//
// [[effects]] built the reads for all four owner kinds and handed the rendering
// over; only the **trait instance** had a surface before this. The author's report
// was the entity kind: *"check `sfx-reveal-entity` … I don't see the SFX rendered
// on their sheet"* — a rule granted to every hidden GMC, available to Lin
// (`gmc-334682729`) and drawn nowhere.
//
// **Why this spec stubs the query.** Not every owner kind has live content to draw
// from, so the stub grafts a granted id onto the entity, its active projection and
// every trait-set setting — the only way to pin those surfaces at all. Because a
// stub can quietly become the only thing that works, the live world is asserted
// separately (`the live world's grant still draws` below) rather than assumed.
//
// **The live case moved, 2026-09-29.** `sfx-gift` now reaches the **asset trait
// set** — measured: `traitSetSettings[ts-3].grantedSfxIds = ['sfx-gift']`, and
// **zero** of Kael's trait settings carry a granted rule. So the granted rule draws
// on the *trait-set* strip, not the trait-instance strip. This spec used to pin the
// trait-instance path from live data on the claim that 889 of 890 granted owners
// were trait settings; that is no longer true, and the assertion was failing for
// the right reason rather than because anything broke.

const KAEL = 'character-kael-drift-e555ccde'

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: KAEL }
})

/** A granted id per owner kind, so every surface has something to draw. */
const GRANTED = {
  entity: 'sfx-reveal-entity',
  projection: 'sfx-hinder',
  traitset: 'sfx-one-trick',
}

/**
 * Let every GraphQL call through, but graft granted ids onto the sheet's entity
 * answer: the entity itself, its active projection, and each of its trait-set
 * settings. Only ids already in the catalog are used, so the cards resolve.
 */
async function stubGranted(page, { grantTraitSet = true } = {}) {
  await page.route('**/api/v1/graphql', async (route) => {
    const res = await route.fetch()
    let body
    try { body = await res.json() } catch { return route.fulfill({ response: res }) }
    const entity = body?.data?.entity
    if (entity) {
      entity.grantedSfxIds = [GRANTED.entity]
      for (const p of entity.projections || []) {
        // Only the body in play draws a strip, so mark the active one.
        if (p.id === entity.currentProjection) p.grantedSfxIds = [GRANTED.projection]
      }
      // Left off by the live test, so that any granted set-level card it sees can
      // only have come from the world rather than from this graft.
      if (grantTraitSet) {
        for (const tss of entity.traitSetSettings || []) tss.grantedSfxIds = [GRANTED.traitset]
      }
    }
    return route.fulfill({ json: body })
  })
}

async function openSheet(page, opts = {}) {
  await asPlayer(page)
  await stubGranted(page, opts)
  await page.setViewportSize({ width: 1280, height: 950 })
  await page.goto('/')
  await page.evaluate((c) => {
    localStorage.setItem('playerId', c.playerId)
    localStorage.setItem('playerName', c.playerName)
    localStorage.setItem('entityId', c.entityId)
  }, character)
  await establishSession(page)
  await page.goto('/')
  await page.waitForTimeout(2000)
  const dot = page.locator('button.map-dot.self').first()
  if (await dot.count()) { await dot.click().catch(() => {}); await page.waitForTimeout(900) }
  await page.waitForFunction(() => !!document.querySelector('.sheet-embedded .header'), null, { timeout: 20_000 })
  await page.waitForTimeout(800)
}

/** Open every collapsed set so the trait-set strips exist. */
async function openAllSets(page) {
  for (let i = 0; i < 12; i++) {
    const t = page.locator('.set-toggle[aria-expanded="false"]').first()
    if (!(await t.count())) break
    await t.click({ timeout: 3000 }).catch(() => {})
    await page.waitForTimeout(200)
  }
  await page.waitForTimeout(400)
}

test('a rule granted to the entity is drawn on the sheet, and not dimmed', async ({ page }) => {
  // The author's exact report, against the live granted read.
  await openSheet(page)
  const m = await page.evaluate(() => {
    const strip = document.querySelector('.sheet-embedded .entity-sfx-cards')
    return {
      hasStrip: !!strip,
      cards: [...(strip?.querySelectorAll('.sfx-card') || [])].map((c) => {
        // What the *granted treatment* costs, isolated: clone the card without the
        // class and compare. A granted card may legitimately be dimmed by its own
        // state — `sfx-blocked` means the rule's conditions do not hold right now —
        // and that is the SFX being unavailable, not the granted mark. [[B189]] is
        // about not adding dimming *for being granted*, which is what this pins.
        const clone = c.cloneNode(true)
        clone.classList.remove('sfx-granted')
        c.parentNode.appendChild(clone)
        const opacityWithout = getComputedStyle(clone).opacity
        const outlineWithout = getComputedStyle(clone).outlineStyle
        clone.remove()
        return {
          text: (c.textContent || '').trim(),
          granted: c.classList.contains('sfx-granted'),
          outlineStyle: getComputedStyle(c).outlineStyle,
          outlineWithout,
          opacity: getComputedStyle(c).opacity,
          opacityWithout,
          title: c.getAttribute('title') || '',
        }
      }),
    }
  })
  expect(m.hasStrip, 'the entity strip renders').toBe(true)
  const granted = m.cards.filter((c) => c.granted)
  expect(granted.length, 'the granted rule is drawn').toBeGreaterThan(0)
  // The dashed edge is the *only* thing the granted treatment changes: the same
  // opacity as the identical card without it, and no dash without it.
  expect(granted.every((c) => c.opacity === c.opacityWithout),
    'granting adds no dimming of its own (B189)').toBe(true)
  expect(granted.every((c) => c.outlineStyle === 'dashed'), 'marked with a dashed edge').toBe(true)
  expect(granted.every((c) => c.outlineWithout !== 'dashed'), 'and the granted mark is what draws it').toBe(true)
  expect(granted.some((c) => /granted to this (entity|body)/.test(c.title)), 'says which owner granted it').toBe(true)
})

test('every owner kind draws its granted rule — entity, body and trait set', async ({ page }) => {
  await openSheet(page)
  await openAllSets(page)
  const m = await page.evaluate(() => {
    const pick = (sel) => [...document.querySelectorAll(sel)].map((c) => ({
      text: (c.textContent || '').trim(),
      granted: c.classList.contains('sfx-granted'),
      dashed: getComputedStyle(c).outlineStyle === 'dashed',
    }))
    return {
      entityOrBody: pick('.sheet-embedded .entity-sfx-cards .sfx-card'),
      traitset: pick('.sheet-embedded .sfx-cards .sfx-card'),
    }
  })
  const dashed = (list) => list.filter((c) => c.granted && c.dashed)

  // The two owner kinds the strip can draw, from the stub: the body in play and
  // the entity itself.
  expect(dashed(m.entityOrBody).length, 'the entity and body owner kinds both draw').toBeGreaterThanOrEqual(2)
  // The trait-set owner kind, from the stub. Deliberately *not* asserted as a live
  // fact here: the stub grants `sfx-one-trick` to every set, so a live grant is
  // indistinguishable from a stubbed one inside this test. The live case is pinned
  // by its own test below.
  expect(dashed(m.traitset).length, 'the trait-set owner kind draws too').toBeGreaterThanOrEqual(1)
  // The **trait-instance** path is deliberately no longer asserted. It was pinned
  // from live data on the claim that Kael's `computer`/`disguise`/`documents`
  // carried a granted `sfx-gift`; `sfx-gift` now reaches the asset trait set
  // instead, and no trait setting holds a granted rule at all — so there is no live
  // case here to pin, and the stub cannot invent one for a field the query does not
  // select. See the header.
})

test("the live world's grant still draws, on the path content now uses", async ({ page }) => {
  // The anti-stub guard. The trait-set graft is switched **off**, so a granted
  // set-level card can only have come from the live world — Kael's `sfx-gift` reach
  // onto the asset trait set. Matching on card *content* is not available: the
  // rendered card has empty text and a generic title, so the stub is turned off
  // rather than told apart.
  await openSheet(page, { grantTraitSet: false })
  await openAllSets(page)
  const dashed = await page.evaluate(() =>
    [...document.querySelectorAll('.sheet-embedded .sfx-cards .sfx-card')]
      .filter((c) => c.classList.contains('sfx-granted')
        && getComputedStyle(c).outlineStyle === 'dashed').length)
  expect(dashed, 'the live granted rule draws on the trait-set strip').toBeGreaterThan(0)
})
