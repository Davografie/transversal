---
title: Private Access Runbook
date: 2026-09-20
last-updated: 2026-09-20
tags:
  - transversal
  - technical
  - security
  - deployment
  - network
  - headscale
aliases:
  - Private Access Runbook
  - Headscale Runbook
  - Remote Access Runbook
status: draft
---

# Private Access Runbook

Standing up **Lane B** from [[Public Exposure Plan]]: a self-hosted private network so the
desktop can be reached from the Pixelbook (and anywhere else) with **no port forwards and nothing
published to the public internet**. Security-owned ([[security]]).

> [!info] What this is and is not
> This is *your* access to the desktop — SSH, the DSH web GUI, and optionally the desktop itself.
> It is **not** how your friends reach the game (that is Lane A, and it needs a per-user identity
> layer this does not provide). The VPS built here is the same one Lane A will later use as its
> public entry, so nothing here is thrown away.

**Decisions locked (2026-09-20):** OVH VPS-1 · domain to be purchased · public DERP relays first,
self-hosted DERP later.

| | |
|---|---|
| Host | OVH VPS-1 — 2 vCore / 4 GB / 40 GB NVMe, unlimited traffic, **€4.57/mo incl. VAT** |
| Domain | not yet owned; ~€10/yr. Needed for the TLS certificate on the control endpoint |
| Software | Headscale **v0.29.3** (pinned), BSD-3-Clause, distroless container |
| Relay | `controlplane.tailscale.com` public DERP initially; self-hosted later |
| Total | **~€65–80/year** |

> [!warning] Status: awaiting hardware
> Steps 1–2 need purchases only the owner can make. Everything from step 3 onward can be executed
> once the VPS exists. Commands below are taken from Headscale's documentation as of 2026-09-20
> (v0.29.x); the container page is community-maintained and not verified by the Headscale authors,
> so confirm anything surprising against `headscale.net/stable/` before trusting it.

## 0 · Why Headscale and not just WireGuard

Plain WireGuard is simpler but is hub-and-spoke with hand-managed keys and no NAT traversal — every
new device is a config edit on every peer. Headscale keeps the same WireGuard data plane but
replaces Tailscale's *coordination server* with your own: device registration, key exchange and ACL
distribution run on your VPS, and the **official Tailscale clients work unmodified**. You keep
Mesh networking and MagicDNS without depending on Tailscale Inc. for the control plane.

Two honest caveats:

- **Relay traffic still uses Tailscale's public DERP servers** until we self-host DERP. That traffic
  is end-to-end encrypted and Tailscale cannot read it, but the dependency is real until step 9.
- **You are your own sysadmin.** If the VPS is down you cannot add or re-register devices — though
  *existing* tunnels keep working, because the data plane is peer-to-peer.

## 1 · Buy the VPS *(owner action)*

1. Order **OVH VPS-1** in the OVH datacentre nearest you (a French or German site keeps latency
   low). 2 vCore / 4 GB is ample: Headscale idles at ~50–100 MB RAM.
2. Choose **Ubuntu 24.04 LTS** (or Debian 12) as the image. Avoid anything with a control panel.
3. Record: the public IPv4, and the root password OVH emails you.

> [!tip] One VPS, two lanes
> Don't buy a bigger box "for later". Lane A's public entry is a reverse proxy plus an outbound
> tunnel — it adds no meaningful load. Size for Headscale and add Lane A for free.

## 2 · Buy a domain *(owner action)*

Needed because the control endpoint must be HTTPS with a **valid certificate**, and Let's Encrypt
will not issue for a bare IP.

1. Register a domain (~€10/yr). Cloudflare Registrar and Porkbun are at-cost or close; any
   registrar is fine — this is not the Cloudflare *service*, just a name.
2. Create an **A record**: `headscale.<yourdomain>` → the VPS IPv4.
3. Optional but recommended: an A record for a future Lane A hostname too, so the name is ready.

**Record for later:** `HEADSCALE_DOMAIN=headscale.example.com`

## 3 · First contact and hardening

> [!important] This box will be internet-facing. Do this before anything else is installed.
> This is the same class of exposure that got the desktop rooted, so the order matters: lock the
> front door *before* putting services behind it.

```bash
# 3.1  From your workstation: create a key if you don't have one, then copy it up
ssh-keygen -t ed25519 -C "transversal-vps"
ssh-copy-id root@<VPS_IP>

# 3.2  Confirm key login works BEFORE disabling passwords (keep this session open)
ssh root@<VPS_IP>

# 3.3  Create the unprivileged admin user
adduser --disabled-password --gecos "" tv2
usermod -aG sudo tv2
rsync --archive --chown=tv2:tv2 ~/.ssh /home/tv2/

# 3.4  Harden sshd — key-only, no root
cat >/etc/ssh/sshd_config.d/99-tv2.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
EOF
sshd -t && systemctl reload ssh

# 3.5  Verify in a SECOND terminal that `ssh tv2@<VPS_IP>` works, then close the root session.
```

**Firewall.** Deny by default; open only what is needed. Do this *before* Headscale is public.

```bash
apt update && apt install -y ufw unattended-upgrades
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp                 # SSH — see the note below
ufw allow 80/tcp                 # ACME HTTP-01, for certificates
ufw allow 443/tcp                # Headscale control + DERP
ufw allow 41641/udp              # WireGuard direct connections
ufw allow 3478/udp               # STUN
ufw enable
ufw status verbose
```

> [!tip] Close port 22 once the tailnet works
> The best SSH hardening available here is to stop exposing SSH to the internet at all. After
> step 8, add `ufw delete allow 22/tcp` and reach the VPS only over the tailnet. Keep one console
> session open while you test that, so you can undo it from OVH's console if it goes wrong.

Enable automatic security updates (this box is now part of your attack surface):

```bash
dpkg-reconfigure -plow unattended-upgrades     # choose "Yes"
```

## 4 · Install Headscale (pinned, confined)

The official image is **distroless** — no shell, no package manager — which is a meaningful
security property. Run it read-only, with no capabilities, published only on loopback; TLS is
terminated by the reverse proxy in step 5.

```bash
sudo mkdir -p /opt/headscale/{config,lib} && cd /opt/headscale

# Pin the version. Never use :latest for internet-facing infrastructure.
curl -fsSL -o config/config.yaml \
  https://raw.githubusercontent.com/juanfont/headscale/v0.29.3/config-example.yaml
```

Edit `config/config.yaml` — the values that matter:

```yaml
server_url: https://headscale.example.com     # must match the DNS name exactly
listen_addr: 127.0.0.1:8080                   # loopback only; Caddy proxies to it
metrics_listen_addr: 127.0.0.1:9090
grpc_listen_addr: 127.0.0.1:50443
# Prefixes are yours to choose; keep them off the LAN ranges you actually use.
ip_prefixes:
  - 100.64.0.0/10
  - fd7a:115c:a1e0::/48
noise:
  private_key_path: /var/lib/headscale/noise_private.key
database:
  type: sqlite
  sqlite:
    path: /var/lib/headscale/db.sqlite
```

`docker-compose.yaml`:

```yaml
services:
  headscale:
    image: docker.io/headscale/headscale:0.29.3   # pinned
    container_name: headscale
    restart: unless-stopped
    read_only: true
    tmpfs:
      - /var/run/headscale
    ports:
      - "127.0.0.1:8080:8080"      # control, loopback only
      - "127.0.0.1:9090:9090"      # metrics, loopback only
    volumes:
      - /opt/headscale/config:/etc/headscale:ro
      - /opt/headscale/lib:/var/lib/headscale
    command: serve
    healthcheck:
      test: ["CMD", "headscale", "health"]
```

```bash
docker compose up -d
docker logs --follow headscale          # Ctrl-C once it reports healthy
curl -s http://127.0.0.1:8080/health
```

## 5 · TLS in front (Caddy)

Caddy with a one-line config obtains and renews the certificate automatically. Headscale keeps
listening on loopback; only Caddy is exposed.

```bash
sudo apt install -y caddy
```

`/etc/caddy/Caddyfile`:

```
headscale.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

```bash
sudo systemctl reload caddy
curl -s https://headscale.example.com/health     # expect OK
```

> [!note] Confirm Headscale's own TLS options at build time
> Headscale's reference has a TLS page; Caddy is used here because it is the least fiddly and
> already needed for Lane A. If you prefer Headscale to terminate TLS itself, verify the current
> config keys against `headscale.net/stable/ref/tls/` rather than trusting this doc.

## 6 · Create the user and first node

```bash
# A Headscale "user" is just an identity bucket; the name must not end with @
docker exec headscale headscale users create tv2
docker exec headscale headscale users list          # note the numeric USER_ID
```

**Desktop (Linux) — this is the machine you want to reach:**

```bash
# Install the official client (must be >= v1.80.0 for Headscale v0.29.x)
curl -fsSL https://tailscale.com/install.sh | sh

sudo tailscale up --login-server https://headscale.example.com
# It prints a URL with an Auth ID; approve it:
#   docker exec headscale headscale auth register --user tv2 --auth-id <AUTH_ID>
sudo tailscale status
```

> [!warning] Check the client version first
> Headscale v0.29.3 declares **"Minimum supported Tailscale client version: v1.80.0"**. An older
> client will fail in confusing ways. Confirm with `tailscale version` before debugging anything else.

## 7 · The Pixelbook

ChromeOS runs the Android Tailscale client, which speaks to Headscale unmodified. Verified against
Headscale's own Android instructions:

1. Install **Tailscale** from the Play Store (or F-Droid).
2. Open the app → settings (top right) → **Accounts**.
3. Kebab menu (⋮) → **Use an alternate server**.
4. Enter `https://headscale.example.com` and follow the prompt.
5. Then approve it on the server: `docker exec headscale headscale auth register --user tv2 --auth-id <AUTH_ID>`.

If the web-auth flow misbehaves — there are **open issues about Android + Headscale + pre-auth
keys**, so treat this as the likeliest snag in the build — use the non-interactive path instead:

```bash
# On the VPS: create a single-use key (default: one use, valid 1 hour)
docker exec headscale headscale preauthkeys create --user <USER_ID>
```

Then in the app: **Accounts → ⋮ → Use an auth key**, paste it, and tap **Log in**.

> [!tip] Test this early, not on the day you travel
> Once both nodes show in `headscale nodes list`, do a real end-to-end test from the Pixelbook on
> mobile data — not home Wi-Fi, where everything works by accident.

## 8 · Reach the desktop, safely

The DSH web GUI is bound to `127.0.0.1:3080` on the desktop — deliberately. Do **not** rebind it to
the tailnet address; publish it with `tailscale serve`, which keeps the loopback binding and adds
TLS on the tailnet so the GUI is never listening on a routable interface:

```bash
# On the desktop
sudo tailscale serve --bg 3080
tailscale serve status
```

Store the SSH keys you already use; Tailscale SSH is optional:

```bash
# Optional: let tailnet identity handle SSH auth (no keys to manage)
sudo tailscale up --ssh --login-server https://headscale.example.com
```

**Acceptance checks — run from the Pixelbook:**

```bash
tailscale status                          # both nodes listed, desktop "online"
tailscale ping <desktop-tailnet-name>     # direct connection, or via DERP relay
ssh <user>@<desktop-tailnet-name>         # terminal works
curl -sI https://<desktop-tailnet-name>/  # DSH GUI responds over the tailnet
```

Once these pass, close the public SSH port (step 3) and confirm you can still get in.

## 9 · Later: self-hosted DERP

Deferred by decision, not forgotten. Replacing Tailscale's public relays removes the last
dependency on their infrastructure. It is another service on this same VPS plus a DNS name and a
certificate — revisit once the tailnet is proven, and confirm the current approach against
`headscale.net/stable/ref/derp/`.

## 10 · Upgrades and upkeep

- **Pin the version.** `0.29.3` in both the image tag and this doc; bump deliberately.
- **Watch releases.** Headscale has shipped CVE batches — 0.28.0 was a *critical* DoS fix — and
  0.29.3 itself carries auth fixes ("a leaked auth ID cannot return the registering user's
  identity"). This is internet-facing software; treat upgrades as routine maintenance.
- Follow the official upgrade steps (`headscale.net/stable/setup/upgrade/`); the SQLite file lives
  in `/opt/headscale/lib`, so back it up before each upgrade.
- `unattended-upgrades` handles the OS; it will not handle the container.

## Rollback

Everything here is reversible: `docker compose down`, `ufw delete allow 443/tcp`, and cancel the
VPS. The domain is reusable for Lane A either way.

## Log

- 2026-09-20 — runbook created. Decisions locked with the owner: OVH VPS-1, domain to be bought,
  public DERP first. Commands taken from Headscale's v0.29.x documentation; client minimum
  (v1.80.0) and the Android pre-auth-key friction recorded as known risks. Awaiting the VPS and
  domain before step 3 can run.
