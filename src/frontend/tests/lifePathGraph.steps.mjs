/**
 * Graph shape of the wrapper-model life-path canvas.
 *
 * The builder now reads `path.steps` / `step.bindings` instead of inferring nodes
 * from `life_path` next_step effects. These assertions pin the four things that
 * changed: nodes are keyed by *step* id, an edge follows a binding's `next`, an
 * exit binding is a terminal rather than an edge, and two steps wrapping the same
 * table stay distinct nodes. A fifth case keeps the bundler fan-in working.
 *
 * The frontend has no test runner (see tests/imageCreditsEditor.autosave.mjs), so
 * this is a standalone script. `lifePathGraph.js` is pure and dependency-free, so
 * plain node runs it:
 *
 *   node src/frontend/tests/lifePathGraph.steps.mjs
 */

import assert from 'node:assert/strict'
import { buildLifePathGraph } from '../src/composables/lifePathGraph.js'

const tables = [
  {
    id: 't-qualify', name: 'Qualify', universe: 'u', scheme: 'RANGE', die: 'd6',
    entries: [
      { key: 'accepted', label: 'Accepted', minValue: 1, maxValue: 3 },
      { key: 'rejected', label: 'Rejected', minValue: 4, maxValue: 6 },
    ],
  },
  {
    id: 't-duty', name: 'Duty', universe: 'u', scheme: 'RANGE', die: 'd6',
    // No authored key: exercises the scheme-derived fallback.
    entries: [
      { key: '', label: 'Serve', minValue: 1, maxValue: 6 },
    ],
  },
]

const path = {
  id: 'p-verdant', name: 'Verdant', entryStep: 's1',
  steps: [
    {
      id: 's1', tableId: 't-qualify', label: 'Qualify', next: '', bindings: [
        { key: 'accepted', next: 's2', exitKind: '', exitPath: '', enroll: true },
        { key: 'rejected', next: '', exitKind: 'muster', exitPath: '', enroll: false },
      ],
    },
    // The same table twice: two steps, one table — distinct nodes.
    { id: 's2', tableId: 't-duty', label: 'First tour', next: 's3', bindings: [] },
    { id: 's3', tableId: 't-duty', label: 'Second tour', next: '', bindings: [] },
  ],
}

const { nodes, edges } = buildLifePathGraph(path, tables)
const byId = new Map(nodes.map((n) => [n.id, n]))

// ── nodes are keyed by step id, not table id ─────────────
assert.deepEqual(
  nodes.filter((n) => n.type === 'rolltable').map((n) => n.id).sort(),
  ['step:s1', 'step:s2', 'step:s3'],
  'one node per step, keyed by step id',
)

// ── two steps wrapping the same table are two distinct nodes ──────
const duty = nodes.filter((n) => n.type === 'rolltable' && n.data.tableId === 't-duty')
assert.equal(duty.length, 2)
assert.notDeepEqual(
  duty[0].position, duty[1].position,
  'two steps wrapping one table must not land on top of each other',
)

// ── an edge follows a binding's `next` (a step id) ────────
const bindingEdge = edges.find((e) => e.source === 'step:s1' && e.target === 'step:s2')
assert.ok(bindingEdge, 'binding accepted.next -> s2 makes the s1 -> s2 edge')
assert.equal(bindingEdge.sourceHandle, 'row-0', 'the edge leaves the bound row')

// ── an exit binding is a terminal, not an edge ────────────
const s1Rows = byId.get('step:s1').data.rows
assert.equal(s1Rows[1].nextTarget, null, 'an exit row has no step target')
assert.deepEqual(s1Rows[1].exit, { kind: 'muster', path: '' }, 'the exit is explicit on the row')
assert.equal(s1Rows[1].via, 'binding')
assert.equal(s1Rows[0].enroll, true)
assert.equal(
  edges.filter((e) => e.source === 'step:s1').length, 1,
  'the exit row contributes no edge',
)

// ── a row with no binding follows the step's default `next` ───────
const defaultEdge = edges.find((e) => e.source === 'step:s2' && e.target === 'step:s3')
assert.ok(defaultEdge, 's2.next -> s3 is the unbound-row default')
assert.equal(byId.get('step:s2').data.rows[0].via, 'default')
assert.deepEqual(
  byId.get('step:s2').data.defaultNext,
  { id: 's3', name: 'Duty', label: 'Second tour' },
)

// ── the key fallback matches the API's row_key() exactly ──────────
assert.equal(
  byId.get('step:s2').data.rows[0].key, '1\u20136',
  'range fallback uses an en-dash (U+2013)',
)
assert.equal(byId.get('step:s1').data.rows[0].key, 'accepted', 'an authored key wins')

// No edge may point at a table-keyed node: ids are steps now.
assert.ok(edges.every((e) => !e.target.startsWith('rt:')), 'no table-keyed edge targets')

// ── several rows converging on one step still fan through a bundler ──
const fan = buildLifePathGraph({
  id: 'p-fan', name: 'Fan', entryStep: 'a',
  steps: [
    {
      id: 'a', tableId: 't-qualify', label: 'A', next: '', bindings: [
        { key: 'accepted', next: 'b', exitKind: '', exitPath: '', enroll: false },
        { key: 'rejected', next: 'b', exitKind: '', exitPath: '', enroll: false },
      ],
    },
    { id: 'b', tableId: 't-duty', label: 'B', next: '', bindings: [] },
  ],
}, tables)

const bundler = fan.nodes.find((n) => n.type === 'bundler')
assert.ok(bundler, 'two rows to one step fan through a bundler')
assert.deepEqual(
  fan.edges.filter((e) => e.target === bundler.id).map((e) => e.sourceHandle).sort(),
  ['row-0', 'row-1'],
)
assert.ok(fan.edges.some((e) => e.source === bundler.id && e.target === 'step:b'))
assert.equal(bundler.data.parentId, 'a', 'the bundler is keyed to the source step')

console.log('lifePathGraph.steps: all assertions passed')

// ── a cycle is still detected and does not break layout ──────────
const cyclic = buildLifePathGraph({
  id: 'p-loop', name: 'Loop', entryStep: 'a',
  steps: [
    { id: 'a', tableId: 't-qualify', label: 'A', next: '', bindings: [
      { key: 'accepted', next: 'b', exitKind: '', exitPath: '', enroll: false },
      { key: 'rejected', next: '', exitKind: 'force_muster', exitPath: '', enroll: false },
    ] },
    { id: 'b', tableId: 't-duty', label: 'B', next: 'a', bindings: [] },
  ],
}, tables)
assert.equal(
  cyclic.nodes.filter((n) => n.type === 'rolltable').length, 2,
  'a cycle still lays out both steps',
)
assert.ok(
  cyclic.edges.some((e) => e.data?.kind === 'back'),
  'the closing edge is marked as a back-edge',
)

console.log('lifePathGraph.steps: cycle assertions passed')
