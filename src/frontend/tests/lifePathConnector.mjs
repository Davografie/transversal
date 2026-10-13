/**
 * The roll-table editor's life-path connector column.
 *
 * These assertions pin the two things the column depends on and the build
 * cannot check: the row-key fallback mirrors the API's `row_key()` exactly
 * (including the en-dash range separator), and the four meanings a binding can
 * have map to the right select token and to the right words. A third block keeps
 * the bound-variables editor's ambient scope in step with the API's
 * `table_bindings()`, which is the authority on what names a path may start from.
 *
 * The frontend has no test runner, so this is a standalone script:
 *
 *   node src/frontend/tests/lifePathConnector.mjs
 */

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  rowKey,
  connectorToken,
  connectorText,
  CONNECTOR_FOLLOW,
  CONNECTOR_END,
} from '../src/composables/lifePathConnector.js'
import { ROLL_TABLE_AMBIENT_VARIABLES } from '../src/composables/rollTableScope.js'

// ── row key: the authored key wins, else the scheme-derived fallback ──
assert.equal(rowKey({ key: 'accepted' }, 7), 'accepted', 'authored key wins')
assert.equal(rowKey({ minValue: 1, maxValue: 3 }), '1\u20133', 'range uses an en-dash')
assert.equal(rowKey({ minValue: null, maxValue: 6 }), '\u20136', 'a one-sided range keeps its blank')
assert.equal(rowKey({ weight: 2 }), 'w2', 'weight')
assert.equal(rowKey({ tier: 'SUCCESS' }), 'SUCCESS', 'tier')
assert.equal(rowKey({}, 4), '4', 'no band falls back to the index')
assert.ok(
  rowKey({ minValue: 1, maxValue: 3 }).includes('\u2013'),
  'the separator is U+2013, matching BAND_SEPARATOR in services/roll_table.py',
)

// ── the select token is one value for the four meanings ──
assert.equal(connectorToken(null), CONNECTOR_FOLLOW, 'no binding follows the step')
assert.equal(connectorToken({ key: 'a', next: 's2' }), 's2', 'a move is the step id')
assert.equal(
  connectorToken({ key: 'a', next: '', exitKind: 'muster' }), 'muster',
  'an exit is its kind',
)
assert.equal(
  connectorToken({ key: 'a', next: '', exitKind: '' }), CONNECTOR_END,
  'a binding with neither ends the term',
)

// ── the read-back line says where the row goes ──
const stepById = new Map([
  ['s1', { id: 's1', label: 'Qualify' }],
  ['s2', { id: 's2', label: '' }],
])
const pathNameOf = (id) => ({ 'lp-muster': 'Muster' }[id] || '')

assert.equal(connectorText(null), 'Follows the step')
assert.equal(
  connectorText({ next: 's1' }, { stepById }), 'Qualify',
  'a move reads the target step label',
)
assert.equal(
  connectorText({ next: 's2' }, { stepById }), 's2',
  'a step with no label falls back to its id',
)
assert.equal(connectorText({ next: 's9' }, { stepById }), 's9', 'an unknown step id reads raw')
assert.equal(connectorText({ next: '', exitKind: 'muster' }), 'Muster out')
assert.equal(connectorText({ next: '', exitKind: 'force_muster' }), 'Muster out (dishonourably)')
assert.equal(
  connectorText({ next: '', exitKind: 'draft', exitPath: 'lp-muster' }, { pathNameOf }),
  'Draft to Muster',
)
assert.equal(
  connectorText({ next: '', exitKind: 'draft', exitPath: '' }, { pathNameOf }),
  'Draft to another path',
)
assert.equal(connectorText({ next: '', exitKind: '' }), 'Ends the term')

// ── the editor's ambient scope mirrors the API's table_bindings() ──
// A roll-table bound variable's path starts from the names `table_bindings()`
// puts in scope before the table's own declarations. Those names are the API's,
// so the frontend mirror is compared against the function itself: a name added
// or removed server-side fails here rather than silently offering a start that
// resolves nothing (or hiding one that would).
const ROLL_TABLE_PY = readFileSync(
  new URL('../../api/src/transversal/services/roll_table.py', import.meta.url),
  'utf8',
)
const apiNames = [...new Set(
  [...ROLL_TABLE_PY.matchAll(/bindings\[\s*["']([^"']+)["']\s*\]\s*=/g)].map((m) => m[1]),
)].sort()
assert.deepEqual(
  Object.keys(ROLL_TABLE_AMBIENT_VARIABLES).sort(),
  apiNames,
  'the editor offers exactly the names table_bindings() binds',
)

console.log('lifePathConnector: all assertions passed')
