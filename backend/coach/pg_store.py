"""
Postgres persistence — the Supabase backend, mirror of store.Store.

Same contract as the SQLite Store (identical public methods), so the rest of
the brain doesn't know or care which one it's talking to (see make_store in
store.py). Differences are confined to this file and are purely dialect:

  * upserts use `INSERT ... ON CONFLICT (...) DO UPDATE` instead of
    SQLite's `INSERT OR REPLACE`;
  * placeholders are `%s`, not `?`;
  * `json` columns are `jsonb`, so reads come back as Python objects
    (validated with `model_validate`) and writes wrap the model's JSON dict
    in `Jsonb(...)`.

Mirror integrity (Section 9.1) is enforced HERE in `save_world`, byte-for-byte
the same rule as the SQLite store — it is pure Python, no SQL. Postgres RLS
cannot express it, so the Python brain stays the only writer. Never point the
iOS client (or PostgREST) at these tables directly.

Connection handling: a small psycopg3 ConnectionPool. `prepare_threshold=None`
disables server-side prepared statements so we are safe behind Supabase's
transaction pooler (pgBouncer), which does not support them. autocommit=True
matches the SQLite store's commit-per-write semantics.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

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

# Tables whose primary key is `user_id` rather than `id`. Mirrors the inline
# set in store.Store._get so key resolution stays identical across backends.
_USER_KEYED = frozenset(
    {"profiles", "programs", "world", "journals", "ai_programs",
     "adjustments", "readiness", "places"}
)

_SCHEMA_FILE = Path(__file__).with_name("schema_postgres.sql")


def _key_col(table: str) -> str:
    return "user_id" if table in _USER_KEYED else "id"


class PgStore:
    def __init__(self, dsn: str, *, min_size: int = 1, max_size: int = 4) -> None:
        self.pool = ConnectionPool(
            conninfo=dsn,
            min_size=min_size,
            max_size=max_size,
            # pgBouncer (Supabase transaction pooler) rejects prepared
            # statements; disabling them keeps us portable across direct and
            # pooled connections. autocommit mirrors SQLite commit-per-write.
            kwargs={"autocommit": True, "prepare_threshold": None},
            open=True,
        )
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        ddl = _SCHEMA_FILE.read_text()
        with self.pool.connection() as conn:
            conn.execute(ddl)

    def close(self) -> None:
        self.pool.close()

    # -- generic helpers -----------------------------------------------------

    def _put(self, table: str, key: str, obj) -> None:
        col = _key_col(table)
        with self.pool.connection() as conn:
            conn.execute(
                f"INSERT INTO {table} ({col}, json) VALUES (%s, %s) "
                f"ON CONFLICT ({col}) DO UPDATE SET json = EXCLUDED.json",
                (key, Jsonb(obj.model_dump(mode="json"))),
            )

    def _get(self, table: str, key: str, model):
        col = _key_col(table)
        with self.pool.connection() as conn:
            row = conn.execute(
                f"SELECT json FROM {table} WHERE {col} = %s", (key,)
            ).fetchone()
        if not row:
            return None
        return model.model_validate(row[0])

    def _all(self, table: str, model) -> list:
        with self.pool.connection() as conn:
            rows = conn.execute(f"SELECT json FROM {table}").fetchall()
        return [model.model_validate(r[0]) for r in rows]

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
        self._put("ai_programs", user_id, program)

    def get_ai_program(self, user_id: str):
        from .ai_program import AIProgram
        return self._get("ai_programs", user_id, AIProgram)

    # -- nudges + verified events -------------------------------------------

    def save_nudge(self, n: Nudge) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO nudges (id, user_id, fired_at, json) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET "
                "user_id = EXCLUDED.user_id, fired_at = EXCLUDED.fired_at, json = EXCLUDED.json",
                (n.id, n.user_id, n.fired_at.isoformat(), Jsonb(n.model_dump(mode="json"))),
            )

    def get_nudge(self, nudge_id: str) -> Nudge | None:
        with self.pool.connection() as conn:
            row = conn.execute("SELECT json FROM nudges WHERE id = %s", (nudge_id,)).fetchone()
        return Nudge.model_validate(row[0]) if row else None

    def recent_nudges(self, user_id: str, limit: int = 20) -> list[Nudge]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT json FROM nudges WHERE user_id = %s ORDER BY fired_at DESC LIMIT %s",
                (user_id, limit),
            ).fetchall()
        return [Nudge.model_validate(r[0]) for r in rows]

    def save_verified_event(self, e: VerifiedEvent) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO verified_events (id, user_id, at, json) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET "
                "user_id = EXCLUDED.user_id, at = EXCLUDED.at, json = EXCLUDED.json",
                (e.id, e.user_id, e.at.isoformat(), Jsonb(e.model_dump(mode="json"))),
            )

    def verified_events_for(self, user_id: str) -> list[VerifiedEvent]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT json FROM verified_events WHERE user_id = %s ORDER BY at ASC",
                (user_id,),
            ).fetchall()
        return [VerifiedEvent.model_validate(r[0]) for r in rows]

    # -- world (mirror-protected) -------------------------------------------

    def get_world(self, user_id: str) -> WorldState | None:
        return self._get("world", user_id, WorldState)

    def save_world(self, w: WorldState, *, growth_event: VerifiedEvent | None = None) -> None:
        """Mirror principle (Section 9.1) — identical rule to the SQLite store."""
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

    # -- program adjustments -------------------------------------------------

    def get_adjustments(self, user_id: str) -> AdjustmentLog:
        log = self._get("adjustments", user_id, AdjustmentLog)
        return log if log is not None else AdjustmentLog(user_id=user_id)

    def save_adjustments(self, log: AdjustmentLog) -> None:
        self._put("adjustments", log.user_id, log)

    # -- iPhone signals: readiness + learned training place -----------------

    def get_readiness(self, user_id: str) -> ReadinessSnapshot | None:
        return self._get("readiness", user_id, ReadinessSnapshot)

    def save_readiness(self, snap: ReadinessSnapshot) -> None:
        self._put("readiness", snap.user_id, snap)

    def get_place(self, user_id: str) -> TrainingPlace | None:
        return self._get("places", user_id, TrainingPlace)

    def save_place(self, place: TrainingPlace) -> None:
        self._put("places", place.user_id, place)

    # -- vitals time series --------------------------------------------------

    def save_vital_samples(self, user_id: str, samples: list[VitalSample]) -> int:
        rows = [
            (user_id, s.metric, s.at.isoformat(), float(s.value), s.unit or "")
            for s in samples
        ]
        with self.pool.connection() as conn:
            conn.cursor().executemany(
                "INSERT INTO vitals (user_id, metric, at, value, unit) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (user_id, metric, at) DO UPDATE SET "
                "value = EXCLUDED.value, unit = EXCLUDED.unit",
                rows,
            )
        return len(rows)

    def vitals_series(
        self, user_id: str, metric: str, since: datetime | None = None,
    ) -> list[VitalSample]:
        with self.pool.connection() as conn:
            if since is not None:
                rows = conn.execute(
                    "SELECT metric, at, value, unit FROM vitals "
                    "WHERE user_id = %s AND metric = %s AND at >= %s ORDER BY at ASC",
                    (user_id, metric, since.isoformat()),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT metric, at, value, unit FROM vitals "
                    "WHERE user_id = %s AND metric = %s ORDER BY at ASC",
                    (user_id, metric),
                ).fetchall()
        return [
            VitalSample(metric=r[0], at=datetime.fromisoformat(r[1]), value=r[2], unit=r[3])
            for r in rows
        ]

    def vitals_metrics(self, user_id: str) -> list[str]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT metric FROM vitals WHERE user_id = %s", (user_id,)
            ).fetchall()
        return [r[0] for r in rows]

    def latest_vital(self, user_id: str, metric: str) -> VitalSample | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT metric, at, value, unit FROM vitals "
                "WHERE user_id = %s AND metric = %s ORDER BY at DESC LIMIT 1",
                (user_id, metric),
            ).fetchone()
        if not row:
            return None
        return VitalSample(metric=row[0], at=datetime.fromisoformat(row[1]), value=row[2], unit=row[3])

    def prune_vitals(self, user_id: str, keep_since: datetime) -> int:
        with self.pool.connection() as conn:
            cur = conn.execute(
                "DELETE FROM vitals WHERE user_id = %s AND at < %s",
                (user_id, keep_since.isoformat()),
            )
            return cur.rowcount

    # -- push device tokens --------------------------------------------------

    def save_push_token(self, user_id: str, token: str, platform: str = "ios") -> None:
        with self.pool.connection() as conn:
            conn.execute(
                "INSERT INTO push_tokens (user_id, token, platform, registered_at) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (user_id, token) DO UPDATE SET "
                "platform = EXCLUDED.platform, registered_at = EXCLUDED.registered_at",
                (user_id, token, platform, datetime.now(timezone.utc).isoformat()),
            )

    def get_push_tokens(self, user_id: str) -> list[str]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "SELECT token FROM push_tokens WHERE user_id = %s", (user_id,)
            ).fetchall()
        return [r[0] for r in rows]

    def delete_push_token(self, token: str) -> None:
        with self.pool.connection() as conn:
            conn.execute("DELETE FROM push_tokens WHERE token = %s", (token,))

    # -- dev affordances ----------------------------------------------------

    def wipe_user(self, user_id: str) -> None:
        """Delete every row owned by this user. Mirrors Store.wipe_user."""
        ident = self.get_identity_for_user(user_id)
        with self.pool.connection() as conn:
            if ident is not None:
                milestone_ids = [
                    m.id for m in self._all("milestones", Milestone)
                    if m.parent_identity_id == ident.id
                ]
                for mid in milestone_ids:
                    habit_ids = [
                        h.id for h in self._all("habits", Habit) if h.parent_milestone_id == mid
                    ]
                    for hid in habit_ids:
                        conn.execute("DELETE FROM habits WHERE id = %s", (hid,))
                    conn.execute("DELETE FROM milestones WHERE id = %s", (mid,))
                conn.execute("DELETE FROM identities WHERE id = %s", (ident.id,))
            for table in (
                "profiles", "programs", "world", "nudges", "verified_events",
                "journals", "readiness", "places", "vitals", "push_tokens",
            ):
                conn.execute(f"DELETE FROM {table} WHERE user_id = %s", (user_id,))

    def dev_force_save_world(self, w: WorldState) -> None:
        """Bypass mirror integrity — for scenario seeding ONLY."""
        self._put("world", w.user_id, w)
