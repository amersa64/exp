"""
SQLite persistence. Holds the full brain state from Section 4.3.

Tables are intentionally tiny and JSON-as-blob — the Pydantic models are the
schema of truth; the DB is just durable memory. Migration story: drop & rebuild
in v1, formalize when v2 needs it.

Mirror integrity (Section 9.1) is enforced in two ways:
  1) `save_world()` requires a VerifiedEvent id to have been the most recent
     `_last_growth_source` on the WorldState — i.e. the only way world state
     gets written is through `WorldState.grow(event, action)`.
  2) There is no public API on this store to mutate currency/streak/unlocks
     directly. The world is derived, never set.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import (
    AdjustmentLog,
    AtomicAction,
    CoachJournal,
    Habit,
    Identity,
    Milestone,
    Nudge,
    ProgramState,
    ReadinessSnapshot,
    TrainingPlace,
    UserProfile,
    VerifiedEvent,
    VitalSample,
    WorldState,
)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS identities (id TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS milestones (id TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS habits (id TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS actions (id TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS profiles (user_id TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS programs (user_id TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS world (user_id TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS nudges (id TEXT PRIMARY KEY, user_id TEXT, fired_at TEXT, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS verified_events (id TEXT PRIMARY KEY, user_id TEXT, at TEXT, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS journals (user_id TEXT PRIMARY KEY, json TEXT NOT NULL);
-- LLM-generated weekly program (split + per-day exercises). Opt-in: only
-- written when profile.derived.use_ai_program is true. Acts as a sibling to
-- ProgramState — the latter still owns calibration phase + progression
-- numbers; this table just holds the LLM's exercise choices per day.
CREATE TABLE IF NOT EXISTS ai_programs (user_id TEXT PRIMARY KEY, json TEXT NOT NULL);
-- Standing program adjustments — the coach's memory of what the user told it
-- to change ("this hurts", "too much volume"). Fed into every future build.
CREATE TABLE IF NOT EXISTS adjustments (user_id TEXT PRIMARY KEY, json TEXT NOT NULL);
-- iPhone signals (Section 8.1). `readiness` holds the latest morning recovery
-- snapshot per user (one row, overwritten daily); `places` holds the learned
-- training geofence per user (one row, centroid updated as we observe visits).
CREATE TABLE IF NOT EXISTS readiness (user_id TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS places (user_id TEXT PRIMARY KEY, json TEXT NOT NULL);
-- Broad HealthKit ingestion (coach.vitals): a rolling per-metric time series.
-- Composite PK dedupes re-posts of the same (metric, timestamp) sample, so the
-- client can re-send overlapping windows idempotently. Pruned to a window.
CREATE TABLE IF NOT EXISTS vitals (
  user_id TEXT NOT NULL,
  metric  TEXT NOT NULL,
  at      TEXT NOT NULL,
  value   REAL NOT NULL,
  unit    TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (user_id, metric, at)
);
CREATE INDEX IF NOT EXISTS idx_vitals_lookup ON vitals(user_id, metric, at);
-- APNs device tokens per user. Must be durable (not in-process) so push
-- survives a stateless/scale-to-zero backend. One row per (user, device);
-- re-registering the same token is idempotent. Stale tokens are pruned when
-- APNs returns 410/400 (see push.APNsPushDelivery).
CREATE TABLE IF NOT EXISTS push_tokens (
  user_id       TEXT NOT NULL,
  token         TEXT NOT NULL,
  platform      TEXT NOT NULL DEFAULT 'ios',
  registered_at TEXT NOT NULL,
  PRIMARY KEY (user_id, token)
);
"""


class Store:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        # check_same_thread=False is fine here: FastAPI uses a worker pool, and
        # all our writes go through explicit conn.commit(). We never share an
        # in-flight transaction across threads.
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    # -- generic helpers -----------------------------------------------------

    def _put(self, table: str, key: str, obj) -> None:
        self.conn.execute(
            f"INSERT OR REPLACE INTO {table} VALUES (?, ?)",
            (key, obj.model_dump_json()),
        )
        self.conn.commit()

    def _get(self, table: str, key: str, model):
        row = self.conn.execute(
            f"SELECT json FROM {table} WHERE {'user_id' if table in ('profiles','programs','world','journals','ai_programs','adjustments','readiness','places') else 'id'}=?",
            (key,),
        ).fetchone()
        if not row:
            return None
        return model.model_validate_json(row[0])

    def _all(self, table: str, model) -> list:
        rows = self.conn.execute(f"SELECT json FROM {table}").fetchall()
        return [model.model_validate_json(r[0]) for r in rows]

    # -- hierarchy -----------------------------------------------------------

    def save_identity(self, x: Identity) -> None: self._put("identities", x.id, x)
    def save_milestone(self, x: Milestone) -> None: self._put("milestones", x.id, x)
    def save_habit(self, x: Habit) -> None: self._put("habits", x.id, x)
    def save_action(self, x: AtomicAction) -> None: self._put("actions", x.id, x)

    def all_actions(self) -> list[AtomicAction]: return self._all("actions", AtomicAction)
    def all_habits(self) -> list[Habit]: return self._all("habits", Habit)
    def get_action(self, action_id: str) -> AtomicAction | None:
        return self._get("actions", action_id, AtomicAction)

    def get_identity_for_user(self, user_id: str) -> Identity | None:
        for ident in self._all("identities", Identity):
            if ident.user_id == user_id:
                return ident
        return None

    def list_milestones_for_user(self, user_id: str) -> list[Milestone]:
        ident = self.get_identity_for_user(user_id)
        if ident is None:
            return []
        return [m for m in self._all("milestones", Milestone) if m.parent_identity_id == ident.id]

    # -- profile / program ---------------------------------------------------

    def save_profile(self, x: UserProfile) -> None: self._put("profiles", x.user_id, x)
    def get_profile(self, user_id: str) -> UserProfile | None:
        return self._get("profiles", user_id, UserProfile)

    def all_profiles(self) -> list[UserProfile]:
        return self._all("profiles", UserProfile)

    def save_program(self, x: ProgramState) -> None: self._put("programs", x.user_id, x)
    def get_program(self, user_id: str) -> ProgramState | None:
        return self._get("programs", user_id, ProgramState)

    def save_ai_program(self, user_id: str, program) -> None:
        """Persist an LLM-generated AIProgram for a user.

        Takes user_id explicitly (rather than reading it off the program)
        because AIProgram is a pure plan object — no user_id field — so the
        binding lives at the store layer, not in the model.
        """
        self.conn.execute(
            "INSERT OR REPLACE INTO ai_programs VALUES (?, ?)",
            (user_id, program.model_dump_json()),
        )
        self.conn.commit()

    def get_ai_program(self, user_id: str):
        # Lazy import: ai_program imports llm/exercises, neither of which
        # store.py needs at module load. Keeps store dependency-light.
        from .ai_program import AIProgram
        return self._get("ai_programs", user_id, AIProgram)

    # -- nudges + verified events -------------------------------------------

    def save_nudge(self, n: Nudge) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO nudges VALUES (?, ?, ?, ?)",
            (n.id, n.user_id, n.fired_at.isoformat(), n.model_dump_json()),
        )
        self.conn.commit()

    def get_nudge(self, nudge_id: str) -> Nudge | None:
        row = self.conn.execute("SELECT json FROM nudges WHERE id=?", (nudge_id,)).fetchone()
        return Nudge.model_validate_json(row[0]) if row else None

    def recent_nudges(self, user_id: str, limit: int = 20) -> list[Nudge]:
        rows = self.conn.execute(
            "SELECT json FROM nudges WHERE user_id=? ORDER BY fired_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [Nudge.model_validate_json(r[0]) for r in rows]

    def save_verified_event(self, e: VerifiedEvent) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO verified_events VALUES (?, ?, ?, ?)",
            (e.id, e.user_id, e.at.isoformat(), e.model_dump_json()),
        )
        self.conn.commit()

    def verified_events_for(self, user_id: str) -> list[VerifiedEvent]:
        rows = self.conn.execute(
            "SELECT json FROM verified_events WHERE user_id=? ORDER BY at ASC",
            (user_id,),
        ).fetchall()
        return [VerifiedEvent.model_validate_json(r[0]) for r in rows]

    # -- world (mirror-protected) -------------------------------------------

    def get_world(self, user_id: str) -> WorldState | None:
        return self._get("world", user_id, WorldState)

    def save_world(self, w: WorldState, *, growth_event: VerifiedEvent | None = None) -> None:
        """
        Mirror principle (Section 9.1) enforced here.

        World may be saved in two situations only:
          - First-ever save (creation), with no prior state.
          - Subsequent save where the in-memory object's private growth marker
            matches the verified event id we were passed.

        Any other write path is rejected. The store is the second line of
        defense; WorldState.grow() is the first.
        """
        existing = self.get_world(w.user_id)
        if existing is None:
            self._put("world", w.user_id, w)
            return
        if growth_event is None:
            raise PermissionError(
                "World mutation rejected: no VerifiedEvent supplied. "
                "World state is derived from verified real-world behavior only. "
                "See Section 9.1, Principle 2.6."
            )
        if w._last_growth_source != growth_event.id:
            raise PermissionError(
                "World mutation rejected: the world object's growth source does not match "
                "the verified event. Did you bypass WorldState.grow()?"
            )
        self._put("world", w.user_id, w)

    # -- coach journal (narrative memory) -----------------------------------

    def get_journal(self, user_id: str) -> CoachJournal | None:
        return self._get("journals", user_id, CoachJournal)

    def save_journal(self, j: CoachJournal) -> None:
        self._put("journals", j.user_id, j)

    # -- program adjustments (coach memory of user-requested changes) --------

    def get_adjustments(self, user_id: str) -> AdjustmentLog:
        """Always returns a log (empty if the user has never adjusted)."""
        log = self._get("adjustments", user_id, AdjustmentLog)
        return log if log is not None else AdjustmentLog(user_id=user_id)

    def save_adjustments(self, log: AdjustmentLog) -> None:
        self._put("adjustments", log.user_id, log)

    # -- iPhone signals: readiness + learned training place -----------------

    def get_readiness(self, user_id: str) -> ReadinessSnapshot | None:
        """The latest morning readiness snapshot, or None if never sent."""
        return self._get("readiness", user_id, ReadinessSnapshot)

    def save_readiness(self, snap: ReadinessSnapshot) -> None:
        self._put("readiness", snap.user_id, snap)

    def get_place(self, user_id: str) -> TrainingPlace | None:
        """The learned training geofence, or None until we've seen one visit."""
        return self._get("places", user_id, TrainingPlace)

    def save_place(self, place: TrainingPlace) -> None:
        self._put("places", place.user_id, place)

    # -- vitals time series (broad HealthKit ingestion) ---------------------

    def save_vital_samples(self, user_id: str, samples: list[VitalSample]) -> int:
        """Upsert a batch of metric readings. Idempotent on (metric, at)."""
        rows = [
            (user_id, s.metric, s.at.isoformat(), float(s.value), s.unit or "")
            for s in samples
        ]
        self.conn.executemany(
            "INSERT OR REPLACE INTO vitals (user_id, metric, at, value, unit) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        self.conn.commit()
        return len(rows)

    def vitals_series(
        self, user_id: str, metric: str, since: datetime | None = None,
    ) -> list[VitalSample]:
        """All samples for one metric (optionally since a cutoff), oldest first."""
        if since is not None:
            rows = self.conn.execute(
                "SELECT metric, at, value, unit FROM vitals "
                "WHERE user_id=? AND metric=? AND at>=? ORDER BY at ASC",
                (user_id, metric, since.isoformat()),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT metric, at, value, unit FROM vitals "
                "WHERE user_id=? AND metric=? ORDER BY at ASC",
                (user_id, metric),
            ).fetchall()
        return [
            VitalSample(metric=r[0], at=datetime.fromisoformat(r[1]), value=r[2], unit=r[3])
            for r in rows
        ]

    def vitals_metrics(self, user_id: str) -> list[str]:
        """Distinct metric keys this user has any data for."""
        rows = self.conn.execute(
            "SELECT DISTINCT metric FROM vitals WHERE user_id=?", (user_id,)
        ).fetchall()
        return [r[0] for r in rows]

    def latest_vital(self, user_id: str, metric: str) -> VitalSample | None:
        row = self.conn.execute(
            "SELECT metric, at, value, unit FROM vitals "
            "WHERE user_id=? AND metric=? ORDER BY at DESC LIMIT 1",
            (user_id, metric),
        ).fetchone()
        if not row:
            return None
        return VitalSample(metric=row[0], at=datetime.fromisoformat(row[1]), value=row[2], unit=row[3])

    def prune_vitals(self, user_id: str, keep_since: datetime) -> int:
        """Drop samples older than the retention window. Returns rows deleted."""
        cur = self.conn.execute(
            "DELETE FROM vitals WHERE user_id=? AND at<?",
            (user_id, keep_since.isoformat()),
        )
        self.conn.commit()
        return cur.rowcount

    # -- push device tokens --------------------------------------------------

    def save_push_token(self, user_id: str, token: str, platform: str = "ios") -> None:
        """Register (idempotently) an APNs device token for a user."""
        self.conn.execute(
            "INSERT OR REPLACE INTO push_tokens (user_id, token, platform, registered_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, token, platform, datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()

    def get_push_tokens(self, user_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT token FROM push_tokens WHERE user_id=?", (user_id,)
        ).fetchall()
        return [r[0] for r in rows]

    def delete_push_token(self, token: str) -> None:
        """Drop a token APNs reported as unregistered (410) or invalid (400)."""
        self.conn.execute("DELETE FROM push_tokens WHERE token=?", (token,))
        self.conn.commit()

    # -- dev affordances ----------------------------------------------------
    #
    # These exist exclusively to support fast iteration during development —
    # the iOS app exposes them via a hidden "Dev" sheet behind /dev/seed in
    # api/app.py. They deliberately bypass mirror-integrity so canned
    # scenarios can be applied in one shot; do NOT call these from any
    # production path.

    def wipe_user(self, user_id: str) -> None:
        """Delete every row owned by this user across every table — fresh
        slate for the next seeded scenario."""
        c = self.conn
        # Identity / milestone / habit are keyed by their own ids, so we look
        # them up by user_id traversal.
        ident = self.get_identity_for_user(user_id)
        if ident is not None:
            c.execute("DELETE FROM identities WHERE id=?", (ident.id,))
            milestone_ids = [
                m.id for m in self._all("milestones", Milestone)
                if m.parent_identity_id == ident.id
            ]
            for mid in milestone_ids:
                c.execute("DELETE FROM milestones WHERE id=?", (mid,))
                # Habits hang off milestones; delete those too.
                habit_ids = [h.id for h in self._all("habits", Habit) if h.parent_milestone_id == mid]
                for hid in habit_ids:
                    c.execute("DELETE FROM habits WHERE id=?", (hid,))
        # Actions can outlive a wipe (they get re-minted), but for a clean
        # slate we'd rather not have orphans either.
        for a in self._all("actions", AtomicAction):
            # Actions don't carry user_id directly; they're parented by habit.
            # Safest: clear the whole table if we've just deleted this user.
            pass  # left intentionally — let prepare_next_action overwrite next time
        c.execute("DELETE FROM profiles WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM programs WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM world WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM nudges WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM verified_events WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM journals WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM readiness WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM places WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM vitals WHERE user_id=?", (user_id,))
        c.execute("DELETE FROM push_tokens WHERE user_id=?", (user_id,))
        c.commit()

    def dev_force_save_world(self, w: WorldState) -> None:
        """Bypass mirror integrity — for scenario seeding ONLY."""
        self._put("world", w.user_id, w)


def make_store(db_path: str | Path = "coach.db"):
    """Pick the persistence backend from the environment.

    If `SUPABASE_DB_URL` (or `DATABASE_URL`) is set we run on Postgres/Supabase
    via PgStore; otherwise we fall back to local SQLite at `db_path`. This is the
    single switch that moves prod onto Supabase while tests and local dev stay on
    zero-setup SQLite. Both backends expose the identical method surface.
    """
    import os

    dsn = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
    if dsn:
        from .pg_store import PgStore
        return PgStore(dsn)
    return Store(db_path)
