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

Options, priced. Verified 2026-09-20; every figure carries a source. Vendors publish in their own
currency and no FX rate was verified, so currencies are reported as published.

| Option | Free tier | First paid tier | Domain needed | Per-user identity | Media / ToS risk |
|---|---|---|---|---|---|
| **Cloudflare Tunnel + Access** | **$0**: 50 users, email-OTP + allowlist IdPs, 1,000 tunnels, 1,000 routes, 100 MB request cap ([plans](https://www.cloudflare.com/plans/zero-trust-services/), [limits](https://developers.cloudflare.com/cloudflare-one/account-limits/)) | Zero Trust Standard **$7/user/mo** | **yes** — a domain in the CF account | **yes, bundled on Free**, deny-by-default | **contractual** — see below; neutralised by R2 |
| **Tailscale Funnel** (public) | **$0** Personal, 6 users, unlimited devices; Funnel on **all plans, beta** ([pricing](https://tailscale.com/pricing), [funnel](https://tailscale.com/docs/features/tailscale-funnel)) | Standard **$8/user/mo** | **no** — and you *cannot* use your own (`tailnet-name.ts.net` only) | **no** — Funnel traffic carries no identity headers and does not work with access controls | no Funnel-specific clause; AUP bars "undue burden"; docs frame Funnel as ephemeral |
| **VPS as public entry** (relay to home) | Oracle Always Free **$0** — with real strings attached, see below ([oracle docs](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)) | **Hetzner cost-optimised from €5.49/mo** + €0.50 IPv4 ([Hetzner price API](https://website-price-api.hetzner.com/api/v1/products/CLOUD_132)); **OVH VPS-1 €3.81 excl. / €4.57 incl. VAT** ([OVH](https://www.ovhcloud.com/en/vps/)); **netcup VPS Lite 1 €4.88/mo incl. VAT** ([netcup](https://www.netcup.com/en/server/vps)); DigitalOcean **$4/mo** ([DO](https://www.digitalocean.com/pricing/droplets)) | recommended | **DIY** — oauth2-proxy / Authelia | none of the CDN kind |

Also-rans: **ngrok is out** — its free plan is 1 GB/mo, below this app's 2–8 GB/mo
([limits](https://ngrok.com/docs/pricing-limits/free-plan-limits)). ZeroTier is a private-lane
tool, not a public front door with identity ([pricing](https://www.zerotier.com/pricing/)).
Fly.io's free tier is gone for new customers (trial only), so it is not a "$0" option either
([pricing](https://fly.io/docs/about/pricing/)).

### Oracle Always Free is weaker than it looks

Verified against [Oracle's Always Free documentation](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
(2026-09-20), because "free forever" is doing a lot of work in that phrase:

- The A1 (ARM) allowance is **1,500 OCPU-hours + 9,000 GB-hours per month — "equivalent to 2 OCPUs
  and 12 GB of memory"** for Always Free tenancies. The often-quoted 4 OCPU / 24 GB is not what the
  docs say today.
- **Idle reclamation is real and documented:** Oracle may reclaim an Always Free instance if, over a
  7-day window, CPU p95 < 20%, network < 20%, and — for A1 shapes — memory < 20%. A nine-person app
  that sits quiet between sessions could plausibly trip that.
- "Out of host capacity" on creation is expected, instances must live in the **home region**,
  outbound TCP/25 is blocked, and only the ephemeral public IP is free.
- The 10 TB/mo outbound allowance is genuine, and far beyond what this app needs.

The AMD micro shape (1/8 OCPU, 1 GB) is not a plausible host for this stack. So Oracle is free on
paper but the least dependable cheap option for something you want always up — worth knowing before
it becomes a game-night outage.

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

## What binds, and what only looks like it does

**Irrelevant at this scale:** Cloudflare's 50-user free cap (9 identities), its 100 MB request cap
(the largest asset is 38 MB), 1,000 tunnels/routes; Tailscale's 6-user cap for the one-person
private lane; ZeroTier's 10 devices; Oracle's 10 TB/mo egress against 2–8 GB.

**Genuinely binding — three things, none of them price:**

1. **Cloudflare's non-HTML CDN clause is the only contractual landmine.** The
   [Service-Specific Terms](https://www.cloudflare.com/service-specific-terms-application-services/#content-delivery-network-free-pro-or-business)
   require paid services to serve "video or a disproportionate percentage of pictures, audio
   files, or other large files", and Cloudflare's own
   [docs](https://developers.cloudflare.com/fundamentals/reference/policies-compliances/delivering-videos-with-cloudflare/)
   confirm **tunnel public hostname routes are subject to it** while *private* network routes are
   exempt. Enforcement is a redirect plus an email notification, not account termination. The 36
   `.webm` files and 10–38 MB animated `.webp` are precisely the named shape.
   **Mitigation:** serve media from **R2**, which the clause itself designates as the compliant
   home — its [free tier](https://developers.cloudflare.com/r2/pricing/) (10 GB-month storage,
   **free egress**, 1M Class A / 10M Class B ops) covers the 742 MB library and 2–8 GB/mo at $0.
2. **Funnel cannot satisfy the requirement.** It is public and carries no identity — Tailscale's
   own comparison notes it "doesn't work with … access controls". With no identity layer, the
   app's single static token is the only gate, which *is* the SEC-3 gap rather than a fix for it.
3. **A public front door wants a domain** (~$11/yr; Cloudflare Registrar is at-cost, Porkbun
   `.com` verified at $11.08/yr). Access requires one; Funnel forbids one entirely.

One structural note: the ComfyUI/GPU pipeline must stay at home, so hosting the app *outright* on
a VPS splits the stack. A VPS is better used as a relay than as a host.

## Recommendation

**Cloudflare Tunnel + Access on the Free plan, with the media library on R2 behind a media
subdomain.** Roughly **$11/yr domain + $0** — and it is the only option that satisfies both hard
requirements (no forwards, real per-user identity) for nine people at no monthly cost. The single
genuine risk is neutralised by R2, which the clause names as the compliant path. Run the agent
unprivileged (`cloudflared tunnel run --token`, or a container) rather than the root service
installer — this box has a compromise history.

**Runner-up:** a cheap VPS as the public entry, relaying to home over WireGuard — **Hetzner from
€5.49/mo**, **OVH VPS-1 €4.57/mo incl. VAT**, or **netcup VPS Lite 1 €4.88/mo incl. VAT** — with
oauth2-proxy or Authelia in front. No media ToS exposure, and the public entry is decoupled from the
home box, so a home outage is a 502 rather than a compromised front door. More setup, more robust
long term. Oracle's Always Free tier is the cheapest on paper but carries the caveats above.

**Regardless of the lane:** Tailscale (free) for the private lane — SSH, this agent GUI, and
desktop access, none of it on the public internet.

## Verification and caveats

Verified 2026-09-20 from vendor sources, and **re-confirmed first-hand** for the two figures that
most affect the decision: Oracle's Always Free allowances and idle-reclamation policy (from Oracle's
own documentation), and Hetzner's cost-optimised server price (from Hetzner's own price API, which
returns €5.49/mo and `active: true`). Also verified: Tailscale's plan limits and Funnel's
constraints; the scope of Cloudflare's tunnel/media terms; Cloudflare Zero Trust's free seat count
and request cap; R2's free tier.

**Sourced from the research stream rather than re-verified here:** the OVH, netcup and
DigitalOcean figures, and the domain renewal prices (Porkbun `.com` $11.08/yr). Treat those as
second-hand until checked at order time.

**Could not verify — not treated as fact:**
- Funnel's numeric bandwidth cap (the docs say only "non-configurable bandwidth limits").
- **Hetzner's orderability**: its price API reports the cost-optimised plans `active`, while its
  plan pages render them as unavailable. Unresolved — check at order time.
- Cloudflare Registrar's exact live `.com` price (dashboard-only; the at-cost policy is what is
  published).
- Whether netcup's "traffic flatrate" has a volume cap.

Currencies are as published by each vendor. The research stream supplied a EUR→USD rate of
1.147723 (2026-09-20), but no conversion was applied to the figures above, so no conversion error
can propagate into them.

## Open decisions

- **Lane A — awaiting your choice.** Recommended: Cloudflare Tunnel + Access (Free) with media on
  R2. Runner-up: a VPS relay. Funnel would need a separate identity layer bolted on first, which
  is most of the work Access already does for free.
- **Lane B** — tailnet for SSH and the agent GUI; the desktop GUI tool is still to pick. `sshd` is
  installed but currently **disabled**.
- Whether to fix SEC-10/SEC-11 before the first external connection (both small).
- If R2 is chosen: mirror the whole library, or only the large and animated assets? The `_Large`
  variants average 82 KB, which is well inside the terms' comfort zone — it is the 10–38 MB
  animated files that give the clause its shape.

## Log

- 2026-09-20 — plan drafted: preconditions tabulated, scale measured from the live media
  library, and the two lanes defined.
- 2026-09-20 — pricing verified and cited (Tailscale, Cloudflare Zero Trust, R2, Oracle, Netcup,
  DigitalOcean, ngrok, ZeroTier). Confirmed from Cloudflare's own documentation that tunnel
  *public hostname* routes are subject to the non-HTML terms while private routes are exempt, and
  identified R2 as the permitted mitigation. Recommendation recorded; the lane choice is the
  user's.
- 2026-09-20 — corrections applied once the VPS research settled. The third-party Hetzner figure
  was **wrong** and is replaced with Hetzner's own price API (€5.49/mo + €0.50 IPv4); Oracle's
  Always Free caveats were added after re-reading Oracle's documentation first-hand — the A1
  allowance is **2 OCPU / 12 GB**, idle reclamation is documented, and "out of host capacity" is
  expected; netcup, OVH and Fly.io figures corrected (Fly's free tier no longer exists for new
  customers). **Recommendation unchanged.**
