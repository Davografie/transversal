# Browser verification (`e2e/`)

Playwright-driven browser checks for the Transversal frontend. This is the project's
**rendering and interaction** verification — the `src/frontend/scripts/check-*.mjs` scripts
remain the dependency-free logic checks.

## Why this lives outside `src/frontend/`

Two concrete reasons, not preference:

1. **The frontend image is `node:22-alpine`** and Playwright does not support its bundled
   browsers on musl/Alpine. Putting them in the app image would mean either an unsupported
   setup or switching the image to a Playwright base — and rebuilding that image means
   recreating the canonical `tv2_frontend` container, which serves `:3000` for everyone.
2. **The frontend Docker build context is `./src/frontend`**, and `COPY . .` would pull a
   nested `node_modules` into the image. Its `.dockerignore` only excludes a *top-level*
   `node_modules`, so a nested one is not covered.

So the browsers run on the **host** (glibc), against whichever server you point it at.

## Running

```bash
cd e2e
npm install                 # first time only
npx playwright install chromium firefox   # first time only
npm test
```

Point it somewhere else with `E2E_BASE_URL`:

```bash
E2E_BASE_URL=http://ptdave:3000 npm test      # over the tailnet, from a remote machine
E2E_BASE_URL=http://localhost:3001 npm test   # the gated prod build
npm run test:chromium                          # one engine only
```

> [!note] Tailnet runs need `allowedHosts`
> Vite answers only hostnames listed in `server.allowedHosts`. `ptdave` and
> `ptdave.ts.transversal.app` are already allowed; a new hostname must be added there first,
> or the page returns `Blocked request. This host is not allowed.` See
> [[Private Access Runbook]].

> [!note] Resolving the tailnet name depends on where you run
> On the desktop itself, `ptdave` resolves because that *is* the machine's hostname — so
> `E2E_BASE_URL=http://ptdave:3000 npm test` works there even though the Tailscale client runs
> with `--accept-dns=false`. From any other device it resolves only if MagicDNS is enabled on
> that client. If a run fails with a name-resolution error rather than a 403, that is the
> cause — use `http://localhost:3000` locally, or the tailnet name on a device with MagicDNS.

## What it covers

`tests/smoke.spec.js` asserts the shell mounts: correct title, `#app` attached, no uncaught
page errors, the identity prompt visible for a fresh browser, and the name field accepting
input. That catches a blank page, a broken build, or a module that fails on boot — the
failures usually reported as "it just doesn't load".

It runs in **both Chromium and Firefox** on purpose: a second engine catches problems
specific to one of them.

## Adding tests

Keep the same discipline as the rest of the repo: assert something specific and observable,
and prefer a test that fails loudly over one that passes vaguely. Screenshots and traces are
retained on failure (`screenshot: 'only-on-failure'`, `trace: 'retain-on-failure'`), which is
usually the fastest way to see what actually rendered — open the last one with
`npm run report`.
