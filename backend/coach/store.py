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
from pathlib import Path
from typing import Iterable

from .models import (
    AtomicAction,
    Habit,
    Identity,
    Milestone,
    Nudge,
    ProgramState,
    UserProfile,
    VerifiedEvent,
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
            f"SELECT json FROM {table} WHERE {'user_id' if table in ('profiles','programs','world') else 'id'}=?",
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

    def save_program(self, x: ProgramState) -> None: self._put("programs", x.user_id, x)
    def get_program(self, user_id: str) -> ProgramState | None:
        return self._get("programs", user_id, ProgramState)

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
