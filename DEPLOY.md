# Deploying The Coach to a Physical iPhone

End-to-end runbook for: backend up on the Mac, iOS app signed and installed on a real device, talking to each other over Wi-Fi.

## TL;DR — just run the script

```bash
./deploy.sh                     # build + install + launch, ensure backend
./deploy.sh --restart-backend   # also kill the running backend first (after backend code changes)
./deploy.sh --backend-only      # skip iOS (backend code change, app is fine)
./deploy.sh --ios-only          # skip backend (UI iteration, backend already up)
```

The script auto-detects your current LAN IP, updates `CoachBackendURL` if it changed, regenerates the Xcode project only when needed, ensures the backend is up on `0.0.0.0:8765`, builds, installs, and launches.

The sections below are for understanding what the script does and for manual recovery when something breaks.

## Prereqs (one-time)

- Xcode + command-line tools (`xcode-select --install`).
- `xcodegen` (`brew install xcodegen`).
- Apple ID added in **Xcode → Settings → Accounts**. Team `7QF5D7PJL5` (Amer / `amer@zaimler.ai`) must be visible there.
- iPhone plugged in via USB, **Developer Mode enabled** on the device (Settings → Privacy & Security → Developer Mode).
- First-ever install on a given device requires manually trusting the developer profile: **Settings → General → VPN & Device Management → Apple Development: amer@zaimler.ai → Trust**.

## Step 0 — Find the Mac's current LAN IP

This is the #1 thing that breaks reruns. The IP changes across networks.

```bash
ipconfig getifaddr en0     # Wi-Fi; use en1 if you're on Ethernet
```

If the result differs from what's in `ios/project.yml` (`CoachBackendURL`), update it before building:

```yaml
# ios/project.yml
CoachBackendURL: http://<MAC_LAN_IP>:8765
```

The phone and Mac must be on the **same Wi-Fi** with **no AP/client isolation** (most home routers are fine; many cafes/hotels block peer-to-peer LAN).

## Step 1 — Bring up the backend

```bash
cd /Users/amer/productivity/the-coach
PYTHONPATH=backend python -m uvicorn api.app:app --host 0.0.0.0 --port 8765
```

`--host 0.0.0.0` is critical — binding to `127.0.0.1` (the README default) leaves it invisible to the phone.

Smoke test from the Mac:

```bash
curl -s http://127.0.0.1:8765/healthz                  # → {"status":"ok"}
curl -s http://<MAC_LAN_IP>:8765/healthz               # → {"status":"ok"}
curl -s -H "X-User-Id: demo-user" http://<MAC_LAN_IP>:8765/world
```

All authenticated endpoints require the `X-User-Id` header; the iOS app sends `demo-user`.

## Step 2 — Find the connected iPhone

```bash
xcrun devicectl list devices
```

Copy the UDID from the previous error log or from Xcode's Devices window — it looks like `00008120-0004046A3613C01E`. That's different from the CoreDevice ID `devicectl` prints; `xcodebuild` wants the UDID.

## Step 3 — Generate Xcode project, build, install, launch

From `ios/`:

```bash
cd /Users/amer/productivity/the-coach/ios

xcodegen generate

xcodebuild \
  -project TheCoach.xcodeproj \
  -scheme TheCoach \
  -configuration Debug \
  -destination 'platform=iOS,id=00008120-0004046A3613C01E' \
  -allowProvisioningUpdates \
  build

APP="$HOME/Library/Developer/Xcode/DerivedData/TheCoach-fzlwldvgekcgqegpfcfqxxqzcmxp/Build/Products/Debug-iphoneos/TheCoach.app"

xcrun devicectl device install app --device 00008120-0004046A3613C01E "$APP"
xcrun devicectl device process launch --device 00008120-0004046A3613C01E ai.zaimler.TheCoach
```

DerivedData hash (`fzlwldvgekcgqegpfcfqxxqzcmxp`) is stable for this project on this Mac. If you nuke DerivedData, find the new path with: `xcodebuild -showBuildSettings | grep TARGET_BUILD_DIR`.

## Step 4 — Verify end-to-end

Watch the backend log for requests from the phone (its IP, not the Mac's):

```bash
tail -f /tmp/coach-backend.log    # if backgrounded via the same redirect
```

You should see `GET /healthz HTTP/1.1 200 OK` from the phone's LAN IP within a few seconds of launch.

## Gotchas already hit (don't repeat)

1. **`CODE_SIGNING_ALLOWED: NO` in `project.yml`** — disables signing entirely, produces an unsigned binary, device rejects with `LaunchExecutableValidationErrorDomain` / "No code signature found". The fix is the current config: `CODE_SIGN_STYLE: Automatic` + `DEVELOPMENT_TEAM: 7QF5D7PJL5`, no `CODE_SIGNING_ALLOWED` override.
2. **Bundle ID collisions** — `com.example.TheCoach` and `com.amer.TheCoach` are both registered elsewhere on Apple's side. Current ID is `ai.zaimler.TheCoach`. If you ever see "app identifier ... cannot be registered", change it to something else unique under your reverse-DNS.
3. **Phone uses `127.0.0.1`** — on a real device, `127.0.0.1` is the phone, not the Mac. The app reads `CoachBackendURL` from `Info.plist`; both `CoachAPI` and `BackendHealth` honor it. Both must use the override or you'll see a misleading "unreachable" banner while the rest of the app works.
4. **First launch after install fails with "Security / invalid code signature"** — that's the untrusted developer profile. Trust it once on the device (see Prereqs). It does not mean signing is broken.
5. **Backend bound to `127.0.0.1`** — the README's quickstart command omits `--host 0.0.0.0`. That works for the simulator but not for a physical phone.
6. **Mac firewall** — currently disabled, so not blocking. If you ever turn it on, allow inbound on 8765 for `python`.

## Tear-down

```bash
# Stop the backend
lsof -tiTCP:8765 -sTCP:LISTEN | xargs kill

# Uninstall from the phone (optional)
xcrun devicectl device uninstall app --device 00008120-0004046A3613C01E --app ai.zaimler.TheCoach
```
