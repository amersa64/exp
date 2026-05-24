"""
Calendar interface (Section 8.1 — Google Calendar read+write).

The real implementation requires OAuth + the user's Google account; that lives
behind this interface. In v0 we ship a Stub that holds events in memory so the
nudge engine and EXECUTE stage are fully exercisable in tests.

Rubric F1/F2: a real calendar adapter is a thin port of these methods.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Protocol


@dataclass
class CalendarEvent:
    id: str
    title: str
    start: datetime
    end: datetime
    is_busy: bool = True


@dataclass
class FreeSlot:
    start: datetime
    end: datetime

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


class CalendarClient(Protocol):
    def events_for(self, user_id: str, day: datetime) -> list[CalendarEvent]: ...
    def find_free_slot(
        self,
        user_id: str,
        earliest: datetime,
        latest: datetime,
        min_minutes: int,
    ) -> FreeSlot | None: ...
    def block(self, user_id: str, title: str, start: datetime, minutes: int) -> CalendarEvent: ...
    def did_event_occur(self, user_id: str, event_id: str) -> bool: ...


# ----------------------------------------------------------------------------
# Stub
# ----------------------------------------------------------------------------

@dataclass
class StubCalendarClient:
    events: dict[str, list[CalendarEvent]] = field(default_factory=dict)
    occurred: set[str] = field(default_factory=set)

    def seed(self, user_id: str, evs: list[CalendarEvent]) -> None:
        self.events.setdefault(user_id, []).extend(evs)

    def events_for(self, user_id: str, day: datetime) -> list[CalendarEvent]:
        d = day.date()
        return [e for e in self.events.get(user_id, []) if e.start.date() == d]

    def find_free_slot(
        self,
        user_id: str,
        earliest: datetime,
        latest: datetime,
        min_minutes: int,
    ) -> FreeSlot | None:
        evs = sorted(
            [e for e in self.events.get(user_id, []) if e.is_busy and e.end > earliest and e.start < latest],
            key=lambda e: e.start,
        )
        cursor = earliest
        for e in evs:
            if e.start >= cursor + timedelta(minutes=min_minutes):
                return FreeSlot(cursor, e.start)
            cursor = max(cursor, e.end)
        if latest >= cursor + timedelta(minutes=min_minutes):
            return FreeSlot(cursor, latest)
        return None

    def block(self, user_id: str, title: str, start: datetime, minutes: int) -> CalendarEvent:
        ev = CalendarEvent(
            id=f"evt-{len(self.events.get(user_id, []))+1}",
            title=title,
            start=start,
            end=start + timedelta(minutes=minutes),
        )
        self.events.setdefault(user_id, []).append(ev)
        return ev

    def mark_occurred(self, event_id: str) -> None:
        self.occurred.add(event_id)

    def did_event_occur(self, user_id: str, event_id: str) -> bool:
        return event_id in self.occurred
