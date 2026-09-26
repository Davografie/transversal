/**
 * Auto-save behaviour of `ImageCreditsEditor` ([[B211]]).
 *
 * The credits editor has no Save button: every edit is PATCHed shortly after you
 * stop typing. That is timing behaviour the production build cannot check — and
 * this script exists because the first version of it crashed on setup with a
 * temporal-dead-zone error (`dirty` declared after the `immediate` watcher that
 * reads it) that the build reported as green.
 *
 * The frontend has **no test runner**, so this is a standalone script rather than
 * a suite: it compiles the SFC to a client component with `@vue/compiler-sfc`
 * (Vite's `ssrLoadModule` gives you the SSR build, which cannot be mounted),
 * mounts it with a stub renderer that captures `addEventListener` and the element
 * handlers, stubs `fetch`, and drives the real handlers.
 *
 * Run it from the frontend image:
 *
 *   docker run --rm \
 *     -v "$PWD/src/frontend/tests:/app/tests:ro" \
 *     -v "$PWD/src/frontend/src:/app/src:ro" \
 *     -w /app transversal2-frontend:latest node /app/tests/imageCreditsEditor.autosave.mjs
 *
 * If the frontend ever grows a real runner, this belongs in it — the stub
 * renderer below is the part worth replacing first.
 */

import assert from 'node:assert/strict'
import { readFileSync, unlinkSync, writeFileSync } from 'node:fs'
import { parse, compileScript } from '@vue/compiler-sfc'
import { createRenderer, h, nextTick } from 'vue'

// ── compile the SFC to a client component, mount it with a stub renderer ──

const filename = '/app/src/components/ImageCreditsEditor.vue'
const { descriptor } = parse(readFileSync(filename, 'utf8'), { filename })
const { content } = compileScript(descriptor, { id: 'credits-autosave', inlineTemplate: true })
// Written inside /app so its bare `vue` import resolves against /app/node_modules.
const compiled = '/app/.imageCreditsEditor.autosave.tmp.mjs'
writeFileSync(compiled, content)
const { default: ImageCreditsEditor } = await import(compiled)

const makeEl = (tag) => ({
  tag, props: {}, children: [], options: [], value: '', text: '', listeners: {},
  // `v-model` on a native element is a directive that attaches its own listener,
  // so the stub has to accept one for the simulation to update the model.
  addEventListener(type, fn) { this.listeners[type] = fn },
  removeEventListener() {},
})

/** Fire a real event: the directive's listener first (it assigns the model), then
 *  the element's own handler — exactly as the DOM dispatches both. */
function fire(el, type) {
  const event = { target: el }
  const captured = el.listeners?.[type]
  if (typeof captured === 'function') captured(event)
  const key = 'on' + type[0].toUpperCase() + type.slice(1)
  const prop = el.props[key]
  for (const fn of Array.isArray(prop) ? prop : [prop]) {
    if (typeof fn === 'function') fn(event)
  }
}

const nodeOps = {
  createElement: makeEl,
  createText: (t) => ({ text: t, props: {} }),
  createComment: (t) => ({ comment: t, props: {} }),
  setText: (n, t) => { n.text = t },
  setElementText: (n, t) => { n.text = t },
  insert: (child, parent, anchor) => {
    child.parent = parent
    const kids = (parent.children ||= [])
    if (anchor) {
      const at = kids.indexOf(anchor)
      kids.splice(at < 0 ? kids.length : at, 0, child)
    } else {
      kids.push(child)
    }
    // `vModelSelect` reads `el.options`, so a select has to see its options.
    if (parent.tag === 'select' && child.tag === 'option') (parent.options ||= []).push(child)
  },
  remove: (child) => {
    const parent = child?.parent
    if (!parent?.children) return
    const at = parent.children.indexOf(child)
    if (at >= 0) parent.children.splice(at, 1)
    const o = (parent.options || []).indexOf(child)
    if (o >= 0) parent.options.splice(o, 1)
  },
  parentNode: (node) => node?.parent || null,
  nextSibling: (node) => {
    const kids = node?.parent?.children
    if (!kids) return null
    return kids[kids.indexOf(node) + 1] || null
  },
  querySelector: () => null,
  setScopeId: () => {},
  cloneNode: (n) => ({ ...n }),
  insertStaticContent: () => makeEl('div'),
  patchProp: (el, key, prev, next) => {
    el.props[key] = next
    // runtime-dom mirrors an option/input `value` onto the element and `_value`.
    if (key === 'value') { el.value = next; el._value = next }
  },
}
const { createApp } = createRenderer(nodeOps)

const walk = (node, out = []) => {
  if (!node || typeof node !== 'object') return out
  out.push(node)
  for (const c of node.children || []) walk(c, out)
  return out
}
const find = (root, pred) => walk(root).find(pred)
const textOf = (root) => walk(root).map(n => n.text || '').join(' ')
const sleep = (ms) => new Promise(r => setTimeout(r, ms))

// ── fetch stub ──
let calls = []
let fail = false
globalThis.fetch = async (url, opts = {}) => {
  calls.push({ url, method: opts.method, body: opts.body ? JSON.parse(opts.body) : null })
  if (fail) return { ok: false, status: 400, json: async () => ({ detail: 'bad url' }) }
  return { ok: true, status: 200, json: async () => ({}) }
}

const props = {
  imageId: 'img-1',
  credits: [{ role: 'artist', name: 'Jane Doe', url: 'https://example.org/jane' }],
  license: 'CC BY-SA 4.0',
  creditText: 'Art by Jane Doe',
}
function mount() {
  const container = makeEl('div')
  const app = createApp({ render: () => h(ImageCreditsEditor, props) })
  app.mount(container)
  return { app, container }
}
const nameInput = (c) => find(c, n => n.tag === 'input' && n.props.placeholder === 'Name')

// ── 1. there is no Save button ──
{
  const { app, container } = mount()
  assert.doesNotMatch(textOf(container), /Save credits/, 'the Save button is gone')
  assert.equal(
    walk(container).find(n => n.tag === 'button' && /save/i.test(n.text || '')),
    undefined,
    'no button mentions saving',
  )
  app.unmount()
}

// ── 2. typing saves, once, after the pause ──
{
  calls = []
  const { app, container } = mount()
  const name = nameInput(container)
  assert.ok(name, 'the name input exists')
  name.value = 'Jane D'
  fire(name, 'input')
  name.value = 'Jane Do'
  fire(name, 'input')
  assert.equal(calls.length, 0, 'nothing is written on the keystroke itself')
  await sleep(650)
  assert.equal(calls.length, 1, 'one request for the burst, not one per letter')
  assert.equal(calls[0].method, 'PATCH')
  assert.match(calls[0].url, /\/api\/v1\/imagen\/img-1$/)
  assert.equal(calls[0].body.credits[0].name, 'Jane Do')
  assert.equal(calls[0].body.license, 'CC BY-SA 4.0')
  assert.equal(calls[0].body.credit_text, 'Art by Jane Doe')
  app.unmount()
}

// ── 3. adding a row is NOT persisted on its own (the server drops blank rows) ──
{
  calls = []
  const { app, container } = mount()
  fire(find(container, n => n.tag === 'button' && /add credit/.test(n.text || '')), 'click')
  await nextTick()
  await sleep(650)
  assert.equal(calls.length, 0, 'an untouched blank row is nothing to save')
  const fresh = walk(container).filter(n => n.tag === 'input' && n.props.placeholder === 'Name').pop()
  fresh.value = 'Anon'
  fire(fresh, 'input')
  await sleep(650)
  assert.equal(calls.length, 1)
  assert.equal(calls[0].body.credits.length, 2, 'both rows are sent')
  app.unmount()
}

// ── 4. removing a row saves straight away ──
{
  calls = []
  const { app, container } = mount()
  fire(find(container, n => n.tag === 'button' && n.props.title === 'Remove this credit'), 'click')
  await sleep(50)
  assert.equal(calls.length, 1, 'removal is not debounced')
  assert.deepEqual(calls[0].body.credits, [])
  app.unmount()
}

// ── 5. closing the panel right after typing still saves ──
{
  calls = []
  const { app, container } = mount()
  const name = nameInput(container)
  name.value = 'Jane Doe!'
  fire(name, 'input')
  assert.equal(calls.length, 0)
  app.unmount()
  await nextTick()
  assert.equal(calls.length, 1, 'the pending edit is flushed on unmount')
  assert.equal(calls[0].body.credits[0].name, 'Jane Doe!')
}

// ── 6. a rejected save surfaces the reason ──
{
  calls = []
  fail = true
  const { app, container } = mount()
  const url = find(container, n => n.tag === 'input' && n.props.placeholder === 'https://…')
  url.value = 'javascript:alert(1)'
  fire(url, 'input')
  await sleep(650)
  assert.equal(calls.length, 1, 'it tried')
  assert.match(textOf(container), /bad url/, 'the server reason is shown')
  app.unmount()
  fail = false
}

unlinkSync(compiled)
console.log('ImageCreditsEditor auto-save: all assertions passed')
