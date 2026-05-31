-- Postgres schema for The Coach — mirror of the SQLite _SCHEMA in store.py.
--
-- Same design: tiny JSON-as-blob tables; the Pydantic models are the schema of
-- truth, the DB is durable memory. The only Postgres-specific choices vs SQLite:
--   * `json` columns are `jsonb` (queryable + renders in the Supabase editor).
--   * upserts use ON CONFLICT (see pg_store.py) instead of INSERT OR REPLACE.
-- Mirror integrity (Section 9.1) is NOT enforced here — it lives in
-- PgStore.save_world(), exactly as it does in the SQLite Store. Postgres RLS
-- cannot express "world may only change via WorldState.grow()", so the Python
-- brain stays the only writer. Do NOT expose these tables via PostgREST.

CREATE TABLE IF NOT EXISTS identities (id text PRIMARY KEY, json jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS milestones (id text PRIMARY KEY, json jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS habits (id text PRIMARY KEY, json jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS actions (id text PRIMARY KEY, json jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS profiles (user_id text PRIMARY KEY, json jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS programs (user_id text PRIMARY KEY, json jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS world (user_id text PRIMARY KEY, json jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS nudges (id text PRIMARY KEY, user_id text, fired_at text, json jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS verified_events (id text PRIMARY KEY, user_id text, at text, json jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS journals (user_id text PRIMARY KEY, json jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS ai_programs (user_id text PRIMARY KEY, json jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS adjustments (user_id text PRIMARY KEY, json jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS readiness (user_id text PRIMARY KEY, json jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS places (user_id text PRIMARY KEY, json jsonb NOT NULL);

CREATE TABLE IF NOT EXISTS vitals (
  user_id text NOT NULL,
  metric  text NOT NULL,
  at      text NOT NULL,
  value   double precision NOT NULL,
  unit    text NOT NULL DEFAULT '',
  PRIMARY KEY (user_id, metric, at)
);
CREATE INDEX IF NOT EXISTS idx_vitals_lookup ON vitals(user_id, metric, at);

-- APNs device tokens per user. Durable so push survives a stateless backend.
CREATE TABLE IF NOT EXISTS push_tokens (
  user_id       text NOT NULL,
  token         text NOT NULL,
  platform      text NOT NULL DEFAULT 'ios',
  registered_at text NOT NULL,
  PRIMARY KEY (user_id, token)
);
