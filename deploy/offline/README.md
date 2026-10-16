# The offline page ([[B88]])

When the machine that runs Transversal is switched off, `transversal.app` used to answer
with **`502 Bad Gateway` and an empty body** — measured: ~3 s (Caddy's dial timeout) and
then a blank page, because the browser received a valid response containing nothing.

This page replaces that. It is served by **Caddy on the VPS**, which is the one part of the
chain that stays up when the desktop is off, so it needs no second host and no DNS change:

```caddy
(offline) {
	handle_errors {
		@away expression {err.status_code} in [502, 503, 504]
		handle @away {
			root * /var/www/offline
			rewrite * /index.html
			file_server
			# Never let the browser hold the offline page once we are back.
			header Cache-Control "no-store"
			header Retry-After "20"
		}
	}
}

transversal.app       { import offline ; ... }
global.transversal.app { import offline ; ... }
playroom.transversal.app { import offline ; ... }
```

Install: copy `index.html` to `/var/www/offline/` on the VPS (`/etc/caddy/Caddyfile` is the
live config; keep the timestamped backup beside it that every edit there makes).

## Two constraints worth remembering

- **Nothing on the page may come from the desktop** — no fonts, no images, no scripts, no
  API call. It is only ever shown when that machine is unreachable, so anything external
  would be a broken asset on top of a broken app. The waveform is inline SVG and the type is
  a system font stack.
- **The service worker must not answer the navigation.** An installed worker serves the
  cached shell for navigations in scope, which would hide this page exactly as it once hid
  the account verify link. `/portal` is denied in `navigateFallbackDenylist`
  (`src/frontend/vite.config.js`) for that reason: the apex root redirects there, and a
  cached shell would boot the app against a dead server instead of showing this.

The copy is in-world on purpose — resonance is the project's own model of what a connection
is ([[Razmerit Resonance]]) — with one quiet factual line at the bottom so a visitor is not
left guessing.
