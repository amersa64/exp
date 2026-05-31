#!/usr/bin/env bash
# Build, install, and launch The Coach on a connected iPhone, and make sure
# the backend is up. Idempotent — safe to re-run after any change.
#
# Usage:
#   ./deploy.sh                  build + install + launch + ensure backend
#   ./deploy.sh --restart-backend  also kill any running backend first
#   ./deploy.sh --backend-only   skip iOS, just (re)start the backend
#   ./deploy.sh --ios-only       skip backend, just build/install/launch

set -euo pipefail

# ---- Project constants (update if your device or team changes) ----
# Optional pin — set this to a specific device identifier (from
# `xcrun devicectl list devices`) if you have multiple iPhones connected
# and want to target a specific one. Leave empty to auto-detect the first
# connected device.
DEVICE_UDID="${DEVICE_UDID:-}"
BUNDLE_ID="ai.zaimler.TheCoach"
SCHEME="TheCoach"
BACKEND_PORT=8765
# -------------------------------------------------------------------

cd "$(dirname "$0")"

# ---- Export COACH_API_TOKEN from .env for xcodegen substitution ----
# xcodegen substitutes ${COACH_API_TOKEN} in ios/project.yml into the app's
# Info.plist so the client can authenticate to the hardened backend. The
# backend itself reads .env directly, so we only need this one var exported
# here. Extracted by prefix-strip (not `source`) to avoid evaluating other
# secrets that may contain shell-special characters.
if [[ -z "${COACH_API_TOKEN:-}" && -f .env ]]; then
    token_line="$(grep -E '^COACH_API_TOKEN=' .env | head -1 || true)"
    [[ -n "$token_line" ]] && export COACH_API_TOKEN="${token_line#COACH_API_TOKEN=}"
fi

RESTART_BACKEND=0
SKIP_IOS=0
SKIP_BACKEND=0
for arg in "$@"; do
    case "$arg" in
        --restart-backend) RESTART_BACKEND=1 ;;
        --backend-only) SKIP_IOS=1 ;;
        --ios-only) SKIP_BACKEND=1 ;;
        -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
        *) echo "Unknown flag: $arg" >&2; exit 2 ;;
    esac
done

step() { printf '\n==> %s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# ---------- 1. Mac LAN IP ----------
IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
[[ -n "$IP" ]] || fail "Could not detect LAN IP on en0 or en1. Are you on Wi-Fi/Ethernet?"
step "Mac LAN IP: $IP"

EXPECTED_URL="http://$IP:$BACKEND_PORT"
REGEN=0

# ---------- 2. Sync CoachBackendURL in project.yml ----------
# Cloud mode: if CoachBackendURL is an https:// URL (e.g. the Fly deployment),
# leave it alone — don't clobber it with the Mac's LAN IP. LAN tethering only
# applies when it's an http:// URL.
CURRENT_URL="$(grep -E 'CoachBackendURL:' ios/project.yml | awk '{print $2}')"
if [[ "$SKIP_IOS" -eq 0 ]]; then
    if [[ "$CURRENT_URL" == https://* ]]; then
        step "CoachBackendURL is a cloud URL ($CURRENT_URL) — leaving it (skipping LAN sync)."
    elif ! grep -q "CoachBackendURL: $EXPECTED_URL\$" ios/project.yml; then
        step "Updating CoachBackendURL -> $EXPECTED_URL"
        # macOS sed: -i '' for in-place without backup
        sed -i '' -E "s|CoachBackendURL: http://[^[:space:]]+|CoachBackendURL: $EXPECTED_URL|" ios/project.yml
        REGEN=1
    fi
fi

# ---------- 3. Backend ----------
if [[ "$SKIP_BACKEND" -eq 0 ]]; then
    BACKEND_PID="$(lsof -tiTCP:$BACKEND_PORT -sTCP:LISTEN 2>/dev/null || true)"

    if [[ -n "$BACKEND_PID" ]] && [[ "$RESTART_BACKEND" -eq 1 ]]; then
        step "Stopping existing backend (PID $BACKEND_PID)"
        kill "$BACKEND_PID"
        # wait up to 5s for it to exit
        for _ in 1 2 3 4 5; do
            kill -0 "$BACKEND_PID" 2>/dev/null || break
            sleep 1
        done
        BACKEND_PID=""
    fi

    if [[ -z "$BACKEND_PID" ]]; then
        step "Starting backend on 0.0.0.0:$BACKEND_PORT"
        PYTHONPATH=backend nohup python -m uvicorn api.app:app \
            --host 0.0.0.0 --port "$BACKEND_PORT" \
            > /tmp/coach-backend.log 2>&1 &
        # wait up to 10s for /healthz
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            sleep 1
            curl -fsS -m 1 "http://127.0.0.1:$BACKEND_PORT/healthz" >/dev/null 2>&1 && break
        done
    fi

    curl -fsS -m 3 "http://127.0.0.1:$BACKEND_PORT/healthz" >/dev/null \
        || fail "Backend not responding. See /tmp/coach-backend.log"
    curl -fsS -m 3 "$EXPECTED_URL/healthz" >/dev/null \
        || fail "Backend not reachable on LAN ($EXPECTED_URL). Check Wi-Fi or firewall."
    step "Backend: up at $EXPECTED_URL"
fi

[[ "$SKIP_IOS" -eq 1 ]] && { step "Done (backend-only)."; exit 0; }

# ---------- 4. Regenerate Xcode project if needed ----------
if [[ "$REGEN" -eq 1 ]] || [[ ! -d ios/TheCoach.xcodeproj ]] \
   || [[ ios/project.yml -nt ios/TheCoach.xcodeproj ]]; then
    step "Regenerating Xcode project"
    (cd ios && xcodegen generate >/dev/null)
fi

# ---------- 5. Device check ----------
# Auto-detect the first connected device if DEVICE_UDID is empty. Lets the
# script survive iPhone upgrades / swaps without editing this file. If
# multiple iPhones are connected, set DEVICE_UDID in the environment.
if [[ -z "$DEVICE_UDID" ]]; then
    # Device names can contain spaces, so awk column slicing is fragile.
    # Extract the UDID by its canonical 8-4-4-4-12 hex format instead.
    DEVICE_UDID="$(xcrun devicectl list devices 2>/dev/null \
        | grep connected \
        | grep -Eo '[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}' \
        | head -1)"
    [[ -n "$DEVICE_UDID" ]] || fail "No connected iPhone detected. Plug it in, unlock, trust the Mac."
    step "Auto-detected device: $DEVICE_UDID"
else
    xcrun devicectl list devices 2>/dev/null | grep -q "$DEVICE_UDID" \
        || fail "Pinned DEVICE_UDID=$DEVICE_UDID is not currently connected."
fi

# ---------- 6. Build ----------
DD="$(pwd)/ios/build"
step "Building (DerivedData: $DD)"
xcodebuild \
    -project ios/TheCoach.xcodeproj \
    -scheme "$SCHEME" \
    -configuration Debug \
    -destination "platform=iOS,id=$DEVICE_UDID" \
    -derivedDataPath "$DD" \
    -allowProvisioningUpdates \
    -quiet \
    build

APP_PATH="$DD/Build/Products/Debug-iphoneos/TheCoach.app"
[[ -d "$APP_PATH" ]] || fail "Built app not found at $APP_PATH"

# ---------- 7. Install + launch ----------
step "Installing on $DEVICE_UDID"
xcrun devicectl device install app --device "$DEVICE_UDID" "$APP_PATH" >/dev/null

step "Launching $BUNDLE_ID"
xcrun devicectl device process launch --device "$DEVICE_UDID" "$BUNDLE_ID" >/dev/null

step "Done. Tail backend log with:  tail -f /tmp/coach-backend.log"
