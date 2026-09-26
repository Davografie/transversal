/**
 * An instance upload must name its rung ([[B212]]).
 *
 * A traitsetting's picture overrides the registry trait's because it is stored on
 * the **setting's** rung of the ladder — `variant_id` = the setting id. If that
 * parameter is ever dropped or misspelled the upload still succeeds: the picture
 * simply lands on the definition rung and nothing overrides, with no error
 * anywhere. That silent failure is why this check exists.
 *
 * A standalone node script (the frontend has no test runner):
 *
 *   docker run --rm \
 *     -v "$PWD/src/frontend/tests:/app/tests:ro" \
 *     -v "$PWD/src/frontend/src:/app/src:ro" \
 *     -w /app transversal2-frontend:latest node /app/tests/imageUpload.variant.mjs
 */

import assert from 'node:assert/strict'
import { uploadImage } from '/app/src/composables/useImageGallery.js'

let seen = null
globalThis.fetch = async (url) => {
  seen = String(url)
  return { ok: true, status: 200, json: async () => ({ image_id: 'probe' }) }
}

// A real id, colons and all: settings are keyed `{entity}:trait-…`.
const setting = 'gmc-3147032:intergalactic-planetary:trait-3160285'
await uploadImage({
  kind: 'trait',
  id: 'trait-3160285',
  variantId: setting,
  universe: 'earth',
  file: { name: 'probe.png' },
})

assert.ok(seen.includes('owner_kind=trait'))
assert.ok(seen.includes('owner_id=trait-3160285'))
assert.ok(seen.includes('universe=earth'))
assert.ok(
  seen.includes('variant_id=' + encodeURIComponent(setting)),
  `the rung must travel in the URL, encoded: ${seen}`,
)

// And a definition upload must NOT name a rung — that is the owner-level picture
// every instance inherits.
seen = null
await uploadImage({ kind: 'trait', id: 'trait-3160285', file: { name: 'p.png' } })
assert.ok(!seen.includes('variant_id'), 'a definition upload must not name a rung')

console.log('uploadImage variant wiring: all assertions passed')
