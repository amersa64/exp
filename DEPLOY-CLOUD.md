# Deploying The Coach to the cloud (stateless brain + Supabase)

The backend is stateless — all state lives in Supabase Postgres — so it can run
on a cheap/free scale-to-zero host. This is the "get it off my laptop" runbook.

Architecture:

```
iPhone ──HTTPS + Bearer token──> brain (Fly.io, scale-to-zero) ──> Supabase Postgres
                                       ▲                                  │
                                       └──── pg_cron POST /scheduler/tick ─┘
                                            (Supabase is the clock + keeps it warm)
```

Pieces in this repo: `Dockerfile`, `.dockerignore`, `fly.toml`,
`backend/coach/pg_cron_setup.sql`. State migration + auth are already done
(see `AGENTS.md` → Persistence / Auth).

---

## 1. Deploy the brain (Fly.io)

Free-friendly: a `shared-cpu-1x` / 256MB machine that scales to zero when idle.

```bash
brew install flyctl        # if needed
fly auth login

# from the repo root (where Dockerfile + fly.toml live):
fly launch --no-deploy --copy-config --name the-coach-brain   # pick your own name
```

Set secrets (never bake these into the image). Pull the values from `.env`:

```bash
fly secrets set \
  SUPABASE_DB_URL="postgresql://postgres.<ref>:<pw>@aws-1-us-east-2.pooler.supabase.com:6543/postgres" \
  COACH_API_TOKEN="<the token in .env>" \
  OPENAI_API_KEY="sk-..." \
  COACH_LLM_PROVIDER="openai" \
  COACH_LLM_MODEL="gpt-5"
  # add ANTHROPIC_API_KEY / RAPID_API_KEY if you use them

fly deploy
```

Verify (note your real `*.fly.dev` host):

```bash
HOST=https://the-coach-brain.fly.dev
curl -s $HOST/healthz                                   # 200, no token (public)
curl -s -o /dev/null -w "%{http_code}\n" $HOST/world -H "X-User-Id: hyper"   # 401 (no token)
curl -s $HOST/world -H "X-User-Id: hyper" -H "Authorization: Bearer <token>" # 200
```

Any Docker host works the same way (Railway, Render, Cloud Run) — same image,
same secrets, just set the platform's port var (the container honors `$PORT`).

## 2. Point the iOS app at it

In `ios/project.yml` set `CoachBackendURL` to your `https://...fly.dev` host,
then rebuild (`./deploy.sh` exports `COACH_API_TOKEN` from `.env` so the app
authenticates). The app already sends the bearer token (`CoachAPI.authorize`).

## 3. Wire the heartbeat (pg_cron)

Once the host URL exists, open `backend/coach/pg_cron_setup.sql`, replace
`<BACKEND_URL>` and `<COACH_API_TOKEN>`, and run it in the Supabase SQL editor
(Dashboard → SQL editor — it runs privileged, which `create extension` needs).
This enables `pg_cron`/`pg_net` and schedules the tick. Confirm with
`select * from cron.job;` and `select * from cron.job_run_details order by start_time desc limit 5;`.

The schedule is UTC — shift the hours in the cron expression to cover your local
daytime.

## 4. Push (APNs) — reach a closed phone

Push is wired end to end (`coach/push.py` → APNs HTTP/2; iOS registers + handles
taps). It activates when the four APNs secrets are set; otherwise the backend
just logs nudges (`LoggingPushDelivery`).

1. **Create the key** at developer.apple.com → Keys → (+) → *Apple Push
   Notifications service (APNs)*. Download `AuthKey_XXXX.p8` once; note the Key ID.
2. **Set the backend secrets** (alongside the others):
   ```bash
   fly secrets set \
     APNS_KEY_P8="$(cat AuthKey_XXXX.p8)" \
     APNS_KEY_ID="XXXXXXXXXX" \
     APNS_TEAM_ID="7QF5D7PJL5" \
     APNS_TOPIC="ai.zaimler.TheCoach" \
     APNS_SANDBOX="true"     # false for TestFlight/App Store builds
   ```
3. **iOS** already carries the `aps-environment: development` entitlement and
   registers its device token to `/push/register` on launch. Use `development`
   + `APNS_SANDBOX=true` for dev-signed builds; switch both to production for
   TestFlight. Device tokens persist in Supabase (`push_tokens`), so push
   survives scale-to-zero; dead tokens are pruned automatically on APNs 410.

The pg_cron tick (step 3) is what actually triggers pushes on schedule — with
APNs configured, a tick that decides to nudge now buzzes the phone. Tighten the
cron to per-workout times (night-before / pre / post) once you're happy.
