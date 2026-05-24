# iOS client (scaffold)

The brain runs server-side (Section 8.3). This client is intentionally thin: it
displays, it pushes one-tap replies, it reads HealthKit, it forwards push
notifications. It does NOT plan.

## Status

These Swift files are **scaffolding** — they need Xcode + Apple Developer
credentials to build, run, and sign for APNs. They're committed so the shape of
the app is concrete and the next developer can open them in Xcode without
guessing layout.

| File | Purpose | Build status |
|------|---------|--------------|
| `TheCoachApp.swift` | App entry, root `WindowGroup`, push registration | scaffold |
| `Views/WorldView.swift` | The four-level zoom (identity → milestone → habit → action) | scaffold |
| `Views/NudgeReplyView.swift` | One-tap reply UI fired from push notification | scaffold |
| `Views/IntakeView.swift` | Conversation, not a form (Rubric B1) | scaffold |
| `Services/CoachAPI.swift` | HTTP client for the backend brain | scaffold |
| `Services/HealthKitService.swift` | HealthKit reads for verification + timing | scaffold |
| `Models/Hierarchy.swift` | Mirror of the backend four-level model | scaffold |

## What you must wire up before this compiles

1. Create an Xcode project (or SwiftPM package) and drop these files in.
2. Apple Developer team + APNs key for push notifications.
3. HealthKit capability + `Info.plist` usage descriptions.
4. Google Calendar OAuth (done server-side — backend handles the token, client
   just sees calendar blocks reflected back through `CoachAPI`).
5. Point `CoachAPI.baseURL` at the backend brain (not yet HTTP-exposed in this
   repo — see `backend/coach/lifecycle.py` for the Python API).

## Mirror principle (Section 9.1) on the client

The client **must not** compute world growth locally. Currency/streak/unlocks
are read-only fields rendered from `GET /world`. The only way they change is a
verified event posted from this app (a one-tap report or a HealthKit signal
forwarded to the backend). If a future change adds a path like `world.currency
+= 1` in Swift, that's the bug from Principle 2.6.
