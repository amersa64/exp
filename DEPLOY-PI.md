# Deploying The Coach to a Raspberry Pi (Always-On, Tailscale-Protected)

End-to-end runbook for migrating the backend off the Mac onto a Raspberry Pi Zero 2 W, exposed **only** over a private Tailscale mesh — never on the public internet.

> **Status:** planned, not yet executed. Pick this up when you have access to the Pi. The current production path is still `DEPLOY.md` (Mac on LAN).

---

## Why this exists

The current setup (`DEPLOY.md`) requires your Mac to be awake and on the same Wi-Fi as the phone. Two problems with that:

1. **Reliability** — Mac sleeps, you change networks, Wi-Fi flakes; the app silently fails.
2. **Reach** — the app only works at home. Cellular or "at the gym" doesn't reach `192.168.x.y`.

The fix is to move the backend onto an always-on host (the Pi Zero 2 W you already own) and reach it from anywhere via Tailscale — a mesh VPN that keeps the port off the public internet entirely.

---

## What we're building

```
┌────────────┐         ┌──────────────────────┐
│  iPhone    │◄────────►│  Pi Zero 2 W         │
│  (anywhere)│ Tailscale│  - FastAPI :8766     │
│            │ WireGuard│  - SQLite (on USB SSD)│
└────────────┘  tunnel  │  - systemd-managed    │
                        └──────────────────────┘
                                  │
                                  ▼
                          OpenAI API (egress only)
```

- **No public IP, no port forwarding, no DNS record.** The Pi's port `8766` exists only on its Tailscale interface (`100.x.x.x`).
- **Auth model:** anything in your tailnet can reach it. The current backend already has no real auth (just the `X-User-Id` header) — tailnet membership *is* the authentication.
- **Optional defense in depth:** small shared-secret header check in FastAPI middleware (see §9 below) — fires if Tailscale ever has an outage or misconfig.

---

## Hardware checklist

| Item | Have? | Notes |
|---|---|---|
| Pi Zero 2 W (quad-core ARMv7/aarch64, 512MB) | ✓ | The original Zero/Zero W won't work — wrong CPU arch for modern Python wheels |
| MicroSD card | needed | **See §1 on wear** — endurance card or, better, USB SSD |
| Power supply (5V 2.5A micro-USB) | needed | Underpowered supplies cause silent crashes |
| USB OTG cable + USB SSD (recommended) | optional | ~$25 for 240GB; biggest reliability win |
| Ethernet (Pi Zero 2 W is Wi-Fi only) | n/a | Wi-Fi is fine for this load |

---

## 1. SD card wear — why this matters

Flash cells have a finite number of write cycles before they fail (cheap consumer cards: ~1k–10k cycles per cell). The Pi OS writes constantly (logs, swap), and your backend writes to SQLite on **every** log/nudge/journal entry. A regular SD card under this load typically fails in **6–24 months** — corruption, unbootable Pi, or read-only filesystem.

**Three fixes, pick one:**

1. **Cheapest, accept it** — keep a spare card, reflash yearly. ~$15/yr, low effort.
2. **Endurance card** — Samsung Pro Endurance or SanDisk High Endurance (~$15). Rated ~100× more writes than cheap cards.
3. **USB SSD (recommended)** — plug a small SSD into the Pi's USB port via OTG cable. Put either just `coach.db` there (easier) or the whole rootfs (more involved but bulletproof). SSDs have ~1000× the write endurance and are far faster. ~$25–40.

If you do option 3 just for the DB: mount the SSD at `/mnt/ssd` and set `COACH_DB=/mnt/ssd/coach.db` in the systemd unit.

---

## 2. How Tailscale works — security model recap

Mesh VPN built on WireGuard. Each device installs the client and authenticates with your account. Devices get a private `100.x.x.x` IP and a magic-DNS hostname (`coach.your-tailnet.ts.net`).

Tailscale's coordination server only helps devices exchange public keys and traverse NATs — **it never sees your traffic**. After handshake, your iPhone talks directly to the Pi over a peer-to-peer WireGuard tunnel. Even Tailscale themselves can't decrypt it.

**Threat model implications:**
- Pi's `8766` port doesn't exist on the public internet. Port scanners can't find it.
- The auth boundary is your Tailscale account login. **Use a strong password + 2FA** on the account you sign up with (Google/Apple/email — recommend Apple).
- If Tailscale's coordinator goes down, existing tunnels keep working; you just can't add new devices until it recovers.

Free for personal use (up to 100 devices on the Personal plan).

---

## 3. Setup, in order

### 3.1 Flash Raspberry Pi OS Lite (64-bit)

- Raspberry Pi Imager → **Raspberry Pi OS Lite (64-bit)** — *must be 64-bit*, 32-bit loses wheel support.
- Click the gear icon and pre-configure:
  - Hostname: `coach`
  - SSH: enabled, public-key auth (paste your Mac's `~/.ssh/id_ed25519.pub`)
  - Wi-Fi: your SSID + password
  - User: `amer` (or similar — avoid `pi`)
  - Locale: matches your timezone

### 3.2 First boot + SSH in

```bash
# From your Mac
ssh amer@coach.local

# On the Pi
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv python3-pip git
```

### 3.3 Move the code over

**Option A — git clone** (if the repo is on GitHub):
```bash
git clone <your-repo-url> ~/the-coach
```

**Option B — rsync from Mac** (current state):
```bash
# From the Mac
rsync -av --exclude='.venv/' --exclude='coach.db' --exclude='__pycache__/' \
  --exclude='ios/build/' --exclude='.git/' \
  ~/productivity/the-coach/ amer@coach.local:~/the-coach/
```

### 3.4 Recreate the venv on the Pi

```bash
# On the Pi
cd ~/the-coach
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Pydantic v2's Rust core has prebuilt aarch64 wheels — install should be fast (~1–2 min).

### 3.5 Copy `.env` over (contains OPENAI_API_KEY)

```bash
# From the Mac — one-time secret transfer
scp ~/productivity/the-coach/.env amer@coach.local:~/the-coach/.env
chmod 600 ~/the-coach/.env  # on the Pi
```

### 3.6 (Optional but recommended) USB SSD for the database

```bash
# On the Pi, plug in the SSD, then:
lsblk                                    # find the device, e.g. /dev/sda1
sudo mkfs.ext4 /dev/sda1                 # ⚠️ wipes the drive
sudo mkdir /mnt/ssd
sudo mount /dev/sda1 /mnt/ssd
sudo chown amer:amer /mnt/ssd
echo "/dev/sda1 /mnt/ssd ext4 defaults,noatime 0 2" | sudo tee -a /etc/fstab
```

The `COACH_DB` env var in the systemd unit will point to `/mnt/ssd/coach.db`.

### 3.7 Install systemd unit (see §6 below for the file)

```bash
sudo cp ~/the-coach/scripts/coach.service /etc/systemd/system/coach.service
sudo systemctl daemon-reload
sudo systemctl enable --now coach
sudo systemctl status coach
journalctl -u coach -f               # tail logs
```

### 3.8 Install Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Note the Pi's Tailscale IP and hostname:
tailscale ip -4                      # e.g. 100.64.12.34
tailscale status                     # shows magic-DNS hostname
```

Click the login link, sign in with your chosen identity provider. The Pi is now in your tailnet.

### 3.9 Install Tailscale on your iPhone

App Store → Tailscale → sign in with the **same account**. The Pi should appear in the device list.

### 3.10 Update iOS app to point at the Pi

In `ios/project.yml`, change `CoachBackendURL`:

```yaml
# Before (LAN):
CoachBackendURL: http://192.168.87.31:8765

# After (Tailscale magic-DNS hostname):
CoachBackendURL: http://coach.your-tailnet.ts.net:8766
```

(Use the actual hostname from `tailscale status`. Port stays 8766 — that's what the systemd unit binds to.)

Then:

```bash
cd ~/productivity/the-coach/ios
xcodegen generate
# rebuild + install via deploy.sh or the manual steps in DEPLOY.md
```

### 3.11 Smoke test

```bash
# From the Mac (Tailscale-connected):
curl -s http://coach.your-tailnet.ts.net:8766/healthz
# → {"status":"ok",...}

# From the phone (LTE, away from home Wi-Fi):
# Open the app → should load /world normally
```

---

## 4. Update `DEPLOY.md`

Once the Pi is the production target, add a note at the top of `DEPLOY.md` saying "primary deployment is now `DEPLOY-PI.md`; this doc retained for local-dev-on-Mac workflows."

---

## 5. iOS app: what changes, what doesn't

| File | Change | Why |
|---|---|---|
| `ios/project.yml` | `CoachBackendURL` → Tailscale hostname:8766 | Phone reaches Pi via tailnet |
| `ios/TheCoach/Services/CoachAPI.swift` | No change | It already reads from Info.plist |
| `deploy.sh` | Update auto-detection logic or remove (no more LAN sniffing needed) | LAN IP discovery is moot once we're on Tailscale |

---

## 6. Drafted systemd unit

Save this at `scripts/coach.service` in the repo, then `sudo cp` it into place during setup.

```ini
[Unit]
Description=The Coach backend (FastAPI)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=amer
Group=amer
WorkingDirectory=/home/amer/the-coach
EnvironmentFile=/home/amer/the-coach/.env
Environment=PYTHONPATH=/home/amer/the-coach/backend
Environment=COACH_DB=/mnt/ssd/coach.db
ExecStart=/home/amer/the-coach/.venv/bin/python -m uvicorn api.app:app \
    --host 0.0.0.0 --port 8766
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/home/amer/the-coach /mnt/ssd
ProtectHome=read-only

[Install]
WantedBy=multi-user.target
```

Notes:
- `--host 0.0.0.0` is intentional — uvicorn binds to all interfaces on the Pi, but **the public-internet interface doesn't exist** (the Pi has no public IP). Tailscale gives it a `100.x.x.x` interface that *is* reachable, and the home LAN interface (`192.168.x.x`) is reachable from home. That's fine and matches the threat model.
- If you want to be extra-strict and bind only to the Tailscale interface, set `--host 100.x.y.z` to the Pi's Tailscale IP. Slight gain, small fragility cost (IP can change on relog).

---

## 7. Drafted deploy script

Save this at `scripts/deploy-to-pi.sh`. Run from the Mac after backend code changes.

```bash
#!/usr/bin/env bash
# Sync backend code to the Pi and restart the service.
# Run from the repo root: ./scripts/deploy-to-pi.sh
set -euo pipefail

PI_HOST="${PI_HOST:-amer@coach.local}"          # override if not using mDNS
PI_PATH="${PI_PATH:-~/the-coach}"

echo "→ Syncing code to ${PI_HOST}:${PI_PATH}"
rsync -av --delete \
    --exclude='.venv/' \
    --exclude='coach.db' \
    --exclude='coach.db-*' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='ios/build/' \
    --exclude='.git/' \
    --exclude='.env' \
    backend/ pyproject.toml \
    "${PI_HOST}:${PI_PATH}/"

echo "→ Reinstalling Python deps (in case pyproject.toml changed)"
ssh "${PI_HOST}" "cd ${PI_PATH} && .venv/bin/pip install -e . --quiet"

echo "→ Restarting coach service"
ssh "${PI_HOST}" "sudo systemctl restart coach"

echo "→ Health check"
ssh "${PI_HOST}" "sleep 3 && curl -sS http://127.0.0.1:8766/healthz"
echo

echo "✓ Deployed."
```

`chmod +x scripts/deploy-to-pi.sh` after creating it.

---

## 8. Updating the Pi later

```bash
# Backend code change:
./scripts/deploy-to-pi.sh

# Pi OS / package updates:
ssh amer@coach.local 'sudo apt update && sudo apt upgrade -y && sudo reboot'
```

---

## 9. Optional: shared-secret header (defense in depth)

If you want a seatbelt for the (unlikely) case Tailscale fails open or you misconfigure something:

1. Generate a token: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
2. Add `COACH_SHARED_TOKEN=<that-value>` to both `.env` (Pi) and `Info.plist` (iOS, via `project.yml`).
3. Add a tiny FastAPI middleware in `backend/api/app.py` that checks `X-Coach-Token` against `os.environ["COACH_SHARED_TOKEN"]` and returns 401 on mismatch. ~5 lines.
4. iOS sends the header on every request in `CoachAPI.swift` (mirror how `X-User-Id` is added).

Belt + suspenders. Optional but cheap.

---

## 10. Verification checklist (after first deploy)

- [ ] `systemctl status coach` shows `active (running)` on the Pi
- [ ] `journalctl -u coach --since '1 minute ago'` shows healthy startup, no tracebacks
- [ ] `curl http://coach.your-tailnet.ts.net:8766/healthz` works from your Mac
- [ ] iOS app on home Wi-Fi loads `/world`, `/session/next` normally
- [ ] iOS app on LTE (turn Wi-Fi off, walk outside) **also** loads `/world` — that's the proof Tailscale is doing its job
- [ ] `sudo ss -tlnp | grep 8766` on the Pi shows the process listening
- [ ] From a non-tailnet device (your phone with Tailscale OFF), `curl http://<pi-tailscale-ip>:8766/healthz` **fails to connect** — that's the proof nothing's exposed publicly
- [ ] (If using USB SSD) `df -h /mnt/ssd` shows expected free space; `ls -la /mnt/ssd/coach.db` exists and is being written to during use

---

## 11. Gotchas to expect

1. **First boot is slow** — Python + Pydantic warmup takes 10–20s on this CPU. Don't panic if `/healthz` doesn't answer for the first 30s after reboot. Systemd's default timeout is fine.
2. **`.env` not loaded** — the backend's autoloader reads from the repo root. Confirm `~/the-coach/.env` exists and is readable by user `amer` (`chmod 600`).
3. **OpenAI calls hang** — Pi has no DNS or transient network problem. Check `dig api.openai.com` from the Pi.
4. **`coach.local` doesn't resolve** — mDNS sometimes flakes on cellular networks or non-Apple routers. Fall back to the Pi's Tailscale hostname (`coach.your-tailnet.ts.net`), which always works.
5. **Wi-Fi drops** — Pi Zero 2 W's Wi-Fi can be twitchy on 5GHz. Force 2.4GHz on your router for that device if you see flapping.
6. **iOS app's `URLCache` for exercise images** — already handled (images come from GitHub CDN, not your backend), so Pi load doesn't affect demo images.

---

## 12. Rollback plan

If anything goes sideways, you can flip back to the Mac/LAN setup in ~30 seconds:

1. Revert `CoachBackendURL` in `ios/project.yml` to the Mac LAN IP.
2. `xcodegen generate && ./deploy.sh` to rebuild the iOS app.
3. Make sure backend is running on the Mac (`./deploy.sh --backend-only`).

The Pi keeps running in the background; you can debug it later without affecting the day-to-day app.
