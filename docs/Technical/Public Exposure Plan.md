---
title: Public Exposure Plan
date: 2026-09-20
last-updated: 2026-09-20
tags:
  - transversal
  - technical
  - security
  - deployment
  - network
aliases:
  - Public Exposure Plan
  - Exposure Plan
  - Going Online
  - Remote Access Plan
status: draft
---

# Public Exposure Plan

How Transversal becomes reachable by the troupe without any inbound port forward, and how the
owner reaches the desktop remotely. Security-owned ([[security]]); findings referenced as
**SEC-n** live in [[Security Posture]].

> [!info] Why no port forwards
> The desktop was root-compromised and has since been reinstalled (verified clean, data
> restored). All router port forwards were disabled as part of that recovery. Both lanes below
> are **outbound-only**, so the forwards stay off permanently — this is an upgrade over the old
> arrangement, not a workaround.

## What is actually being asked for

"Public" is the wrong frame. The requirement is *reachable by named friends*, not *reachable by
anyone*. The app has no per-user identity (SEC-3): one static `ACCESS_TOKEN` is the only
credential, it never rotates, and it cannot be revoked for one person. So the honest options are:

- **Bring your own identity at the edge** (Cloudflare Access, or a tailnet) and the app stays
  private-to-invited even though it has a public hostname.
- **Genuinely public** (Tailscale Funnel) and the single static token is the entire gate — fine
  for a trusted group, unacceptable as a standing posture for a box with this history.

That distinction, not the price, is the real decision.

## Preconditions before anything is exposed

| Gate | State |
|---|---|
| SEC-1 AQL injection (data-destructive) | **done** — `515c2fe4` |
| SEC-2 ungated dev API on the LAN | **done** — `515c2fe4` |
| SEC-5 fail-open gate / cleartext cookie | **done** — `515c2fe4` |
| SEC-4 upload traversal + SVG XSS | **done** — `515c2fe4` |
| SEC-10 media served as `application/octet-stream` | open — must precede `nosniff` |
| SEC-11 regex shadows `/media/` for some extensions | open |
| TLS on the public leg | supplied by the tunnel lane |
| SEC-3 per-user identity at the app | open — compensated by edge identity, see above |
| SEC-7 wildcard CORS, SEC-9 no lockfile | open, cheap, independent |

## Traffic and scale (measured 2026-09-20)

The library is 742 MB across 4,978 files, but **what a client actually pulls per scene is small**:

| Asset class | count | total | average |
|---|---|---|---|
| Large variant (1024px) — the scene background | 1,144 | 91.7 MB | **82 KB** |
| Small (240px) / Mini (48px) variants | 2,288 | 10.0 MB | 8.3 KB / 0.7 KB |
| `.webm` animations | 36 | 50.2 MB | 1.4 MB |
| animated `.webp` (played on demand) | 7 | 34.2 MB | 5.0 MB |
| flat/legacy full-size files | 359 | 391.5 MB | 1.1 MB |

All URLs are content-hashed and served `Cache-Control: immutable`, and the app is a PWA, so a
given asset crosses the wire **once per device**.

Working estimate for a session (1 GM + ~6 players):

- scene changes: ~20 backgrounds × 6 clients × 82 KB ≈ **10 MB**
- animations: ~10 plays × 6 clients × ~3 MB ≈ **180 MB**
- cold first visit for a new device: on the order of **50–100 MB**, then cached

So roughly **0.2 GB per session, under 1–2 GB per month** for the whole troupe. Occasional
animated assets reach 38 MB ([[Media Pipeline]]), which is why the *max request* matters more
than the average.

> [!important] What this means for choosing a tier
> At 1–2 GB/month the **bandwidth and egress caps of every candidate are irrelevant** — including
> free tiers. Storage caps are irrelevant (assets are served from the desktop, not the vendor).
> The constraints that actually bind are:
> 1. does the tier allow **real per-user identity** in front of the app (the SEC-3 gap);
> 2. is a **custom domain required**, and what does it cost per year;
> 3. **acceptable-use terms** for proxying large non-HTML assets (webp/webm);
> 4. can the agent run as a **non-root per-user service** (least privilege on a box with a
>    compromise history).
>
> Price is a tiebreaker here, not the decider: every option's entry tier is plausibly affordable
> at this scale.

## Lane A — public entry point for the troupe

Architecture, once a lane is chosen:

1. Edge terminates TLS and performs identity (Access policy / tailnet ACL).
2. An outbound-only agent on the desktop forwards to the **gated prod** surface.
3. `frontend-prod` (`:3001`) rebinds to `127.0.0.1` — it is reachable only by the agent, not by
   the LAN. This is the step deliberately deferred until the tunnel exists.
4. The dev server (`:3000`) stays loopback-always; `DEV_BIND_ADDR=0.0.0.0` remains the explicit
   mobile-testing opt-in (SEC-2).
5. The agent runs as a **user** service, not root, and is pinned to `127.0.0.1:3001`.

Options under consideration, with current prices to be verified and cited:

| Option | Per-user identity | Custom domain | ToS risk for media | Non-root agent |
|---|---|---|---|---|
| Cloudflare Tunnel + Access | yes (bundled identity layer) | required | to verify (non-HTML/§2.8 clause) | yes |
| Tailscale Funnel | no (public endpoint) | not required | to verify | yes |
| VPS (reverse proxy or host) | depends on what you run | required | none | yes |

## Lane B — the owner's own remote access (Pixelbook 2017)

Private lane, one user. A tailnet is the natural fit: outbound-only WireGuard mesh, device-level
SSO, no port forward, and it covers all three needs at once —

- **SSH** to the desktop (enable `sshd`, key-only, or use tailnet-identity SSH so there are no
  keys to manage). `sshd` is currently installed but **disabled**.
- **This agent GUI** (`127.0.0.1:3080`) via `tailscale serve`, which publishes it to the tailnet
  over HTTPS *without* rebinding it or touching LAN exposure.
- **Desktop GUI**, if wanted: Sunshine/Moonlight or RustDesk bound to the tailnet address, or
  Chrome Remote Desktop (zero config from ChromeOS, but outsources the auth decision to Google).

Free-tier limits (user/device counts) are part of the pricing verification below.

## Acceptance checks once wired

```bash
# the app is not on the LAN any more
ss -tln | grep -E ':3001|:3000'        # both 127.0.0.1
# the public hostname is gated by the edge identity layer
curl -s -o /dev/null -w '%{http_code}\n' https://<hostname>/api/v1/graphql   # 401/403 without Access
# the app gate still works behind the tunnel, and the cookie is Secure on the HTTPS leg
curl -s -D- -o /dev/null "https://<hostname>/enter?t=<token>" | grep -i set-cookie
# media still serves correctly through the tunnel
curl -s -o /dev/null -w '%{http_code}\n' https://<hostname>/media/<asset>.webp
```

## Cost

Being verified against current vendor pages; figures will be cited here with URLs when they
land, together with free-tier user/device limits and the ToS clauses that apply. No price is
recorded yet rather than record an unverified one.

## Open decisions

- Lane A: Cloudflare Tunnel + Access (recommended — it supplies the identity layer the app
  lacks) versus Tailscale Funnel (no domain, but genuinely public) versus a VPS.
- Lane B: tailnet for SSH + agent GUI; desktop GUI tool still to pick.
- Whether to fix SEC-10/SEC-11 before the first external connection (they are small).

## Log

- 2026-09-20 — plan drafted: preconditions tabulated, scale measured from the live media
  library, and the two lanes defined. Pricing section pending verification.
