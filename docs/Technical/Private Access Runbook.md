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

> [!note] Which account are you? Two different worlds
> **Bare/minimal images:** you log in as `root` with the password the host emailed you, and
> steps 3.3–3.5 below create an unprivileged admin user.
>
> **Ubuntu cloud images** (what OVH ships on a VPS): the password belongs to **`ubuntu`**, not
> `root`. `root` login is refused, and `ubuntu` already has passwordless sudo. In that case skip
> 3.3 entirely — keep `ubuntu` as the admin user — and install your key with
> `ssh-copy-id -i ~/.ssh/<key>.pub ubuntu@<IP>`.
>
> This runbook was first executed against an OVH VPS, so the `ubuntu` path is the one that is
> field-tested; the `root` path is the generic case.

> [!warning] sshd overrides must sort BEFORE cloud-init's
> Ubuntu's `/etc/ssh/sshd_config` does `Include /etc/ssh/sshd_config.d/*.conf` **at the top**, and
> sshd honours the **first** value it reads for any keyword. `50-cloud-init.conf` sets
> `PasswordAuthentication yes`, so a `99-transversal.conf` override **loses** despite looking more
> specific. Name it `10-transversal.conf` so it sorts first.
>
> Then verify the *effective* configuration — `sshd -t` only checks syntax and will report success
> while your setting has no effect at all:
>
> ```bash
> sudo sshd -T | grep -iE '^(passwordauthentication|permitrootlogin)'
> ```

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

## 3.5 · Rehearse it locally first — no VPS required

Before you rent anything, prove the whole thing works. `deploy/headscale/rehearse.sh` stands up
Headscale and three real Tailscale client nodes on a private Docker network — nothing exposed, no
domain, no certificate — and asserts that the ACL genuinely **denies** a node owned by another
user:

```bash
bash deploy/headscale/rehearse.sh
```

It checks that the config loads, that the policy parses, that the client meets the version floor,
that all three nodes register with the right owner, and that a same-owner path is **allowed** while
a cross-owner path is **denied in both directions**. It cleans up after itself and exits non-zero
on failure.

This is worth running every time you touch `config.yaml` or `acl.hujson`. It has already caught a
stale config key, a fatal DNS setting, and a policy-file mistake — all of which would otherwise have
surfaced on the VPS. Note the assertion design: a denial is only accepted on the client's actual
denial string, because a check that passes on *any* error output would happily "verify" a
completely broken tailnet.

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

Empty `config/config.yaml` and substitute the prepared files instead of editing by hand:

```bash
cp /path/to/repo/deploy/headscale/config.yaml config/config.yaml
cp /path/to/repo/deploy/headscale/acl.hujson  config/acl.hujson
sed -i 's/headscale\.example\.com/headscale.YOURDOMAIN/g; s/ts\.example\.com/ts.YOURDOMAIN/g' \
    config/config.yaml
```

Full copies live in `deploy/headscale/`, so this step is copy-and-run. The values that matter —
all verified against the upstream v0.29.3 example file:

```yaml
server_url: https://headscale.example.com     # must match the DNS name exactly
listen_addr: 127.0.0.1:8080                   # loopback only; Caddy proxies to it
metrics_listen_addr: 127.0.0.1:9090
grpc_listen_addr: 127.0.0.1:50443
prefixes:                 # NOT `ip_prefixes` — that key is stale
  v4: 100.64.0.0/24
  v6: fd7a:115c:a1e0::/64
  allocation: sequential
noise:
  private_key_path: /var/lib/headscale/noise_private.key
database:
  type: sqlite
  sqlite:
    path: /var/lib/headscale/db.sqlite
policy:
  mode: file
  path: /etc/headscale/acl.hujson
```

> [!warning] Config keys are version-specific, and some mistakes are fatal
> `ip_prefixes` (a list) is now `prefixes` (a `v4`/`v6` map), and similar renames have happened
> before. An earlier draft of this runbook had the stale key — re-check against the upstream
> example on every upgrade rather than assuming a key still exists.
>
> Two more traps, both hit for real while rehearsing this config:
> - **`override_local_dns` defaults to `true`.** If you disable MagicDNS or remove the nameservers
>   without also setting it false, Headscale **refuses to start**:
>   `Fatal config error: dns.nameservers.global must be set when dns.override_local_dns is true`.
> - **Duplicate YAML keys are fatal.** `mapping key "dns" already defined at line 24`. Most YAML
>   consumers silently take the last value; Headscale will not start. Edit sections in place —
>   never append a second copy of one.

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

### The access policy — default-deny

`config/acl.hujson` (copied above) restricts the tailnet to your own devices. This is the step that
makes "no ACL" into "only the owner", and the semantics are worth stating precisely:

- Headscale loads **no policy by default, which means allow-all traffic between nodes.** Supplying
  this file flips the tailnet to **default-deny** — anything not granted is dropped.
- The one rule is `tv2@` → `tv2@`: nodes owned by your Headscale user may reach each other, and
  nothing else. It uses `grants` rather than the legacy `acls` section, per upstream guidance
  (Tailscale considers ACLs legacy and is not adding features to them).

Failure behaviour was **verified against the real v0.29.3 binary**, because "what happens if I get
it wrong" is the part that actually matters:

| Situation | Observed behaviour |
|---|---|
| Malformed policy at **startup** | Headscale **refuses to start**, with a parse error naming line and column. Fails closed and loud. |
| Malformed policy on **reload** | Logged as `ERR reloading policy error="…"` and **the process keeps running**. Whether the previous policy is still enforced could not be conclusively determined — `headscale policy get` reads the file from disk, so it is not evidence. |

Because of that second row, validate *before* you reload. The command exists but talks to the
running instance over its Unix socket, so it has to run inside the container:

```bash
docker exec headscale headscale policy check --file /etc/headscale/acl.hujson
#   -> "Policy is valid", or a parse error naming the line and column

docker kill --signal=HUP headscale          # reload, not restart
docker logs --tail 20 headscale             # confirm the reload succeeded
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

> [!note] Headscale can terminate TLS itself — Caddy is still the better fit
> Verified against the v0.29.3 config: built-in ACME exists (`acme_url`, `acme_email`,
> `tls_letsencrypt_hostname`, `tls_letsencrypt_challenge_type: HTTP-01`), so Caddy is not strictly
> required. It is used anyway because **only one service can hold port 443**, and Lane A will need
> a reverse proxy there — so Caddy is pulled forward rather than adding a migration later. If you
> prefer the built-in route, drop Caddy and set `tls_letsencrypt_hostname`, leaving
> `listen_addr` on `0.0.0.0:443`.

> [!note] A startup warning you should expect, not chase
> Headscale logs `WRN listening without TLS but ServerURL does not start with http://` because it
> serves plain HTTP on loopback while `server_url` is `https`. **That is correct** when a reverse
> proxy terminates TLS — it is not a misconfiguration, and chasing it would mean giving up the
> loopback binding.

## 6 · Create the user and first node

```bash
# A Headscale "user" is just an identity bucket; the name must not end with @
docker exec headscale headscale users create tv2
docker exec headscale headscale users list          # note the numeric USER_ID
```

**Desktop (Linux) — this is the machine you want to reach:**

```bash
# Install the official client (must be >= v1.80.0 for Headscale v0.29.x)
#
# Debian / Ubuntu / Fedora / RHEL etc — the vendor script:
curl -fsSL https://tailscale.com/install.sh | sh
#
# Arch / Omarchy — the vendor script does NOT support Arch. It fails with
# "Couldn't determine what kind of Linux is running" (OS=other-linux) and installs
# nothing at all. Tailscale is in the official 'extra' repo; on Omarchy use its wrapper:
#     omarchy pkg add tailscale        # or: sudo pacman -S tailscale
#     sudo systemctl enable --now tailscaled

# Join. --accept-dns=false keeps Tailscale from rewriting this machine's DNS settings.
sudo tailscale up --login-server https://headscale.example.com --accept-dns=false
# It prints a URL with an Auth ID; approve it:
#   docker exec headscale headscale auth register --user tv2 --auth-id <AUTH_ID>
sudo tailscale status
```

> [!warning] The vendor install script is Linux-distro-specific
> It supports Debian/Ubuntu and RHEL/Fedora families only. On anything else it prints
> `Couldn't determine what kind of Linux is running` and exits without installing — which is
> exactly what happened on the Omarchy (Arch) desktop. Use the distro's own package manager
> instead; Tailscale ships in Arch's `extra` repository.

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
# On the VPS: create a pre-auth key
docker exec headscale headscale preauthkeys create --user <USER_ID>
```

> [!warning] Pre-auth keys are single-use by default
> One key, one device — a second node using the same key fails with **`authkey already used`**, and
> the client just sits there logged out. Either mint a key per device, or pass `--reusable` when
> you create it. Confirm what is outstanding with `headscale preauthkeys list` (note: it takes no
> `--user` flag, unlike `create`).

Then in the app: **Accounts → ⋮ → Use an auth key**, paste it, and tap **Log in**.

> [!tip] Test this early, not on the day you travel
> Once both nodes show in `headscale nodes list`, do a real end-to-end test from the Pixelbook on
> mobile data — not home Wi-Fi, where everything works by accident.

## 8 · Reach the desktop, safely

The DSH web GUI is bound to `127.0.0.1:3080` on the desktop — deliberately. Do **not** rebind it to
the tailnet address; publish it with `tailscale serve`, which leaves the loopback binding intact:

```bash
# On the desktop
sudo tailscale serve --bg --http=3080 3080
tailscale serve status
#   -> Available within your tailnet:
#        http://<desktop>:3080/ (tailnet only)
#        |-- / proxy http://127.0.0.1:3080
```

Then from the Pixelbook: `http://<desktop-tailnet-name>:3080/`

> [!warning] `--http` is REQUIRED with Headscale — the HTTPS form fails
> Verified against Headscale v0.29.3. Plain `tailscale serve` fails, because it asks the control
> plane for a TLS certificate for the tailnet name and Headscale does not implement that endpoint:
>
> ```
> $ tailscale cert <node>.<base-domain>
> 500 Internal Server Error: your Tailscale account does not support getting TLS certs
>
> $ tailscale serve --bg 3080
> error enabling https feature: ... No serve config
> ```
>
> `tailscale serve --bg --http=<port> <target>` **does** work and was confirmed serving. This is not
> a security downgrade: the traffic rides the WireGuard tunnel, which is already encrypted, so
> plain HTTP *inside* the tunnel is not exposed. The same missing-certificate limitation rules out
> Tailscale Funnel, which Headscale does not support at all.
>
> If you later want HTTPS on the GUI itself, terminate it on the desktop with a local reverse proxy
> and a self-signed or locally-trusted certificate — do not expect `tailscale cert` to provide one.

> [!warning] Reach it by tailnet NAME, not by IP
> `tailscale serve` matches on the **Host** header. Verified on the live deployment:
>
> | Request | Result |
> |---|---|
> | `http://ptdave:3080/` | **401** — reaches the app (which then asks for its own token) |
> | `http://ptdave.ts.transversal.app:3080/` | **401** — same |
> | `http://100.64.0.1:3080/` | **404 page not found** — serve rejects the request |
>
> So the URL must use the MagicDNS **name**, which means the *client* side needs MagicDNS enabled.
> Connecting by tailnet IP looks exactly like a broken service and is not one. This cost a round of
> debugging: a test node with `--accept-dns=false` reached the name only via the IP and got a 404.
>
> The DSH GUI also has its **own** token auth (`dsh web authentication required; reopen the URL
> printed by dsh web`). That is expected and separate from the tailnet — the tailnet proves *which
> devices* may connect; the token is the app's own gate.

Store the SSH keys you already use; Tailscale SSH is optional:

```bash
# Optional: let tailnet identity handle SSH auth (no keys to manage)
sudo tailscale up --ssh --login-server https://headscale.example.com
```

**Acceptance checks — run from the Pixelbook:**

```bash
tailscale status                            # both nodes listed, desktop "online"
tailscale ping <desktop-tailnet-name>       # direct connection, or via DERP relay
ssh <user>@<desktop-tailnet-name>           # terminal works
curl -sI http://<desktop-tailnet-name>:3080/   # DSH GUI responds over the tailnet
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

## 11 · Removing a device (lost laptop, stolen phone)

Revocation is the whole reason to run your own control plane, so know it before you need it.
Verified against the live server:

```bash
# Nodes with their numeric IDs
docker exec headscale headscale nodes list

# Revoke by NUMERIC ID — this is the form that works
docker exec headscale headscale nodes delete --identifier <ID> --force

# Remove a user entirely, and its nodes with it
docker exec headscale headscale users destroy --name <USER> --force
```

> [!warning] `--identifier` wants the numeric ID, and failure is quiet
> Passing a hostname there does not work. If you also suppress stderr — as I did in a cleanup
> script — it fails **silently**, and the run looks successful while the device stays registered.
> A cleanup of mine appeared to succeed and left three nodes on the tailnet. Always re-run
> `nodes list` afterwards and confirm with your own eyes that the device is gone.

## Rollback

Everything here is reversible: `docker compose down`, `ufw delete allow 443/tcp`, and cancel the
VPS. The domain is reusable for Lane A either way.

## Log

- 2026-09-20 — runbook created. Decisions locked with the owner: OVH VPS-1, domain to be bought,
  public DERP first. Commands taken from Headscale's v0.29.x documentation; client minimum
  (v1.80.0) and the Android pre-auth-key friction recorded as known risks.
- 2026-09-21 — **deployed.** Owner bought an OVH VPS (`vps-305e1870.vps.ovh.net`,
  <vps-ip-redacted>) and the domain `transversal.app`, with `<control-plane-redacted>` → the VPS.
  Steps 3–5 executed against the real box: key-only SSH with password and root login disabled,
  ufw default-deny, unattended-upgrades, Docker + Caddy + pinned Headscale v0.29.3, and a real
  Let's Encrypt certificate issued automatically by Caddy. `https://…/health` → 200.
- 2026-09-21 — **production verified end-to-end** with three throwaway clients joined to the live
  server over real TLS: same-owner path pinged (`pong`), cross-owner denied in both directions
  (`no matching peer`). All test nodes and the temporary user were then removed; only `tv2`
  remains.
- 2026-09-21 — **reboot test passed.** With no human involved, docker, caddy, ufw and sshd all
  returned `active`, the container came back healthy via its restart policy, and HTTPS served 200
  again. The lane survives a host reboot unattended — which is the point of having it.
- 2026-09-21 — outstanding: the desktop and Pixelbook still need to join (owner action). Awaiting the VPS and
  domain before step 3 can run.
