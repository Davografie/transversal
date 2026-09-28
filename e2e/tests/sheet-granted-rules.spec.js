import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { asPlayer } from '../helpers/role.js'

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
// **Why this spec stubs the query.** Measured across the live world, the 890 owners
// holding a granted rule are **889 trait settings and 1 entity** — there is no
// projection and no trait-set case in any content, so those two surfaces could
// never be pinned by rendering real data. The stub adds a granted id to each owner
// kind on one sheet, which is the only way to cover them at all; the entity and
// trait-instance halves are then also checked against what the live world returns,
// so the stub cannot quietly become the only thing that works.

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
async function stubGranted(page) {
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
      for (const tss of entity.traitSetSettings || []) tss.grantedSfxIds = [GRANTED.traitset]
    }
    return route.fulfill({ json: body })
  })
}

async function openSheet(page) {
  await asPlayer(page)
  await stubGranted(page)
  await page.setViewportSize({ width: 1280, height: 950 })
  await page.goto('/')
  await page.evaluate((c) => {
    localStorage.setItem('playerId', c.playerId)
    localStorage.setItem('playerName', c.playerName)
    localStorage.setItem('entityId', c.entityId)
  }, character)
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
      // The trait-instance path effects already had, from the live world: Kael's
      // `computer` / `disguise` / `documents` are granted `sfx-gift`.
      traitInstance: pick('.sheet-embedded .trait-row .sfx-cards .sfx-card'),
    }
  })
  const dashed = (list) => list.filter((c) => c.granted && c.dashed)

  // The two owner kinds the strip can draw, from the stub: the body in play and
  // the entity itself.
  expect(dashed(m.entityOrBody).length, 'the entity and body owner kinds both draw').toBeGreaterThanOrEqual(2)
  // The trait-set owner kind — no live rule grants to one, so the stub is the only
  // way this surface can be pinned at all.
  expect(dashed(m.traitset).length, 'the trait-set owner kind draws too').toBeGreaterThanOrEqual(1)
  // And the kind that already worked must keep working, from real data: this is the
  // guard for the `.sfx-granted` rule moving into the shared stylesheet.
  expect(dashed(m.traitInstance).length, 'the trait-instance path still draws, from live data').toBeGreaterThan(0)
})
