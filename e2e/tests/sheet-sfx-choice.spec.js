import { test, expect } from '@playwright/test'
import { gql } from '../helpers/sheet.js'
import { asPlayer } from '../helpers/role.js'
import { establishSession } from '../helpers/session.js'

// A choice raised **from the sheet** is answered *as the sheet's body*, not floated
// over it ([[B230]]'s sheet host, handed to [[character-sheet]] 2026-09-28).
//
// The author's report: *"I was expecting the choice table to temporarily replace the
// active modal while the user was making their choice, but now it's rendered
// transparently over the trait row. I expect it to look pretty much the same as the
// life path roll tables in the character sheet panel."* Both halves of that are
// asserted here, because both were wrong and each fails on its own:
//
//   - **placement** — it took `position: absolute; right/bottom: 12px; z-index: 40`,
//     so it lay *over* the trait that raised it instead of taking the body every other
//     sheet view takes. Its own background is `--overlay-2` (two percent opaque), so
//     the rows showed through it: unreadable over its own context, and a click that
//     looked like it had done nothing.
//   - **chrome** — `EffectTargetWizard` draws a card, which is right in the roller and
//     the menus but wrong in a panel that already *is* the container. The life path's
//     table is flat in this same panel; `embedded` makes this one flat too.
//
// The choice is delivered by stubbing the SSE stream rather than by firing a real SFX:
// an SFX whose `choose` has more than one candidate is content, and a layout rule must
// not depend on live session state to be checkable (the same reason `sfx-rail.spec.js`
// stubs `activeSfx`).

const KAEL = 'character-kael-drift-e555ccde'

let character
test.beforeAll(async ({ request }) => {
  const { players } = await gql(request, `query { players { id name agency { entityId main } } }`)
  const owner = players.find((p) => (p.agency || []).some((a) => a.entityId === KAEL && a.main))
  if (!owner) throw new Error(`no player mains ${KAEL} — cannot reach the testing character`)
  character = { playerId: owner.id, playerName: owner.name, entityId: KAEL }
})

/** A structured choice, shaped exactly as `_emit_pending_choices` publishes it. */
function structuredChoice(origin) {
  return {
    origin,
    structured: true,
    element: 'trait_setting',
    candidates: [
      { id: 'c1', name: 'Rhys Iron Roots', subtitle: 'PC · main' },
      { id: 'c2', name: 'Bowen Deer', subtitle: 'GMC' },
      { id: 'c3', name: 'Ren Ruogang', subtitle: 'PC · support' },
    ],
    count: 1,
    field: '',
    step_index: 0,
    source_kind: 'trait_setting',
    source_id: `${KAEL}:trait-1838664:05612764`,
    source_sfx_id: 'sfx-gift',
    answers_so_far: [],
    sfx_name: 'Gift',
    sfx_description: 'Give a trait of yours to another occupant — it leaves you.',
    effect: { type: 'modify_trait', action: 'move' },
  }
}

/**
 * Open the sheet with `choices` pending, delivered `delayMs` after the stream opens.
 *
 * The delay is what lets one page show both states: the sheet renders its ordinary
 * body first, then the question lands in it — which is exactly the transition the
 * author described, and lets the two boxes be compared on one layout rather than
 * across two loads.
 */
async function openSheet(page, choices, delayMs = 0) {
  await asPlayer(page)
  await page.route('**/api/v1/stream**', async (route) => {
    if (delayMs) await new Promise((r) => setTimeout(r, delayMs))
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
      body: `event: sfx_choice_required\ndata: ${JSON.stringify({
        entity_id: KAEL, universe: 'earth', choices,
      })}\n\n`,
    })
  })
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
  if (await dot.count()) { await dot.click().catch(() => {}); await page.waitForTimeout(800) }
  await page.waitForFunction(() => !!document.querySelector('.sheet-embedded .header'), null, { timeout: 20_000 })
  await page.waitForTimeout(600)
}

function box(el) {
  if (!el) return null
  const b = el.getBoundingClientRect()
  return { x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height), bottom: Math.round(b.bottom) }
}

async function measure(page) {
  return page.evaluate(() => {
    const el = (sel) => document.querySelector(sel)
    const style = (node) => {
      if (!node) return null
      const cs = getComputedStyle(node)
      return {
        position: cs.position,
        zIndex: cs.zIndex,
        background: cs.backgroundColor,
        borderTopWidth: cs.borderTopWidth,
        overflowY: cs.overflowY,
      }
    }
    const b = (node) => {
      if (!node) return null
      const r = node.getBoundingClientRect()
      return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height), bottom: Math.round(r.bottom) }
    }
    const host = el('.sheet-sfx-choice')
    const eth = el('.sheet-sfx-choice .etw-root')
    // What is actually painted at the choice's own centre — the whole question of
    // "does it replace the sheet or lie on top of it".
    let atCentre = null
    if (eth) {
      const r = eth.getBoundingClientRect()
      const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)
      atCentre = hit ? `${hit.tagName}.${hit.className}` : null
    }
    return {
      header: b(el('.sheet-embedded .header')),
      body: b(el('.sheet-embedded .sheet-scroll')) || b(host),
      host: b(host),
      hostStyle: style(host),
      sheetWizard: style(eth),
      atCentre,
      candidates: document.querySelectorAll('.sheet-sfx-choice .etw-candidate').length,
      cancel: !!document.querySelector('.sheet-sfx-choice .etw-cancel'),
      rollerWizard: style(el('.sfx-choice-panel .etw-root')),
    }
  })
}

/** The same sheet with nothing pending — the body the traits list would take. */
test('a sheet-raised choice takes the sheet body, flat, like the life path table', async ({ page }) => {
  // The question lands a beat after the sheet is up, so this one page shows both
  // the body it replaces and the body it becomes.
  await openSheet(page, [structuredChoice('sheet')], 3000)
  const bare = await measure(page)
  await page.waitForSelector('.sheet-sfx-choice', { timeout: 15_000 })
  await page.waitForTimeout(400)
  const m = await measure(page)

  expect(m.host, 'the choice renders in the sheet').not.toBeNull()
  expect(m.candidates, 'and shows its candidates').toBe(3)
  expect(m.cancel, 'with a way out').toBe(true)

  // Placement: the body the traits list would have taken, not a floating card.
  expect(m.hostStyle.position, 'the choice is in the sheet flow, not positioned').toBe('static')
  expect(m.hostStyle.zIndex, 'and claims no stacking layer of its own').toBe('auto')

  // It must sit *below* the sheet's header, not over it, and reach the bottom.
  expect(m.host.y, 'it starts where the sheet body starts').toBeGreaterThanOrEqual(m.header.bottom)
  expect(m.host.h, 'it takes the body, not a corner of it').toBeGreaterThan(m.header.h * 2)

  // …and it is what is painted there. The old overlay's own background was 2%
  // opaque, so the rows it covered showed through it; this asserts the surface at
  // the choice's centre is the choice.
  expect(m.atCentre, 'the choice is what you see, not the row behind it').toContain('etw-')

  // Chrome: flat, exactly as the life path's table is flat in this same panel.
  expect(m.sheetWizard.background, 'no card of its own in the sheet').toMatch(/rgba\(0, 0, 0, 0\)|transparent/)
  expect(m.sheetWizard.borderTopWidth, 'and no outline either').toBe('0px')

  // "Pretty much the same as the life path" stated as a measurement: the question
  // fills the very slot the reader's trait list was filling.
  expect(bare.body, 'the bare sheet had that body to give').not.toBeNull()
  for (const key of ['x', 'y', 'w', 'h']) {
    expect(m.host[key], `${key} matches the body the traits list had`).toBe(bare.body[key])
  }
  expect(m.hostStyle.overflowY, 'and it scrolls like that body').toBe('auto')
})

test('the same choice in the roller still arrives as a card', async ({ page }) => {
  // The guard for the half a static check cannot hold: `embedded` must stay opt-in,
  // or the roller and the menus lose the card they are built around.
  await openSheet(page, [structuredChoice('roll')])
  const m = await measure(page)
  expect(m.rollerWizard, 'the roller renders its own copy').not.toBeNull()
  expect(m.rollerWizard.background, 'and it still draws a card').not.toMatch(/rgba\(0, 0, 0, 0\)/)
  expect(m.rollerWizard.borderTopWidth, 'with its border').toBe('1px')
  // No card inside the sheet, because this choice is not the sheet's to answer.
  expect(m.host, 'the sheet host stays empty for a roll-origin choice').toBeNull()
})
