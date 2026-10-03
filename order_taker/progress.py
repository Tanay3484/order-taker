"""Plain-English progress feed for an intake run (004).

Agents never build user-facing strings themselves: they call `feed.say(key, **values)`
and the words come from TEMPLATES below (PRG-3). A test checks every template
against a list of technical words (PRG-4)."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator, Literal

from pydantic import BaseModel

HEARTBEAT_SECONDS = 15.0  # PRG-5; tests patch this

Kind = Literal["info", "working", "done", "warn", "error", "summary", "draft_ready"]

TEMPLATES: dict[str, list[str]] = {
    "started": ["Got it! Reading {count} new messages…"],
    "started_one": ["Got it! Reading 1 new message…"],
    "nothing_new": ["There's nothing new here. I've already gone through all of these messages."],
    "skipped": ["Skipped {count} messages I've already gone through before."],
    "skipped_one": ["Skipped 1 message I've already gone through before."],
    "people": ["Found messages from {count} people: {names}."],
    "people_one": ["Found messages from {names}."],
    "sorter_skipped": ["Reading each person's messages in one go."],
    "reading": ["Reading {name}'s messages…"],
    "helper_down": ["The AI helper isn't running. Please start it and try again."],
    "run_failed": ["Something went wrong while reading the messages. Please try again."],
    "sorted.chit_chat": ["{name} is just chatting. Nothing to order."],
    "sorted.question": ["{name} has a question. I've put it aside for you to reply."],
    "sorted.new_order": ["{name} wants to order something. Writing down the details…"],
    "sorted.change": ["{name} wants to change an order. Working out what's different…"],
    "sorted.cancel": ["{name} wants to cancel an order. Finding which one…"],
    "still_working": [
        "Still working on {name}'s messages, nearly there…",
        "{name}'s messages are taking a little longer. Still on it…",
        "Still reading {name}'s messages carefully…",
    ],
    "draft.new": ["{name}'s order is ready for you to check."],
    "draft.update": ["{name}'s change is ready for you to check."],
    "draft.cancel": ["{name}'s cancellation is ready for you to check."],
    "draft.none": ["{name}'s messages didn't have an order in them after all."],
    "flag": ["Something to check on {name}'s order: {flag}"],
    "failed": ["I couldn't make sense of {name}'s messages. I've put them aside for you to check yourself."],
    "summary": ["All done in {duration}: {parts}."],
    "summary_empty": ["All done in {duration}. Nothing new to order."],
    # pieces of the summary line: (one, many)
    "part.drafts": ["1 thing to check", "{n} things to check"],
    "part.questions": ["1 message needs a reply", "{n} messages need a reply"],
    "part.chatting": ["1 just chatting", "{n} just chatting"],
    "part.failed": ["1 I couldn't read", "{n} I couldn't read"],
    "dur.seconds": ["1 second", "{n} seconds"],
    "dur.minutes": ["1 minute", "{n} minutes"],
}


def render(key: str, variant: int = 0, **values) -> str:
    options = TEMPLATES[key]  # KeyError on an unknown key is deliberate
    return options[variant % len(options)].format(**values)


def plural(key: str, n: int) -> str:
    return render(key, 0 if n == 1 else 1, n=n)


def duration(seconds: float) -> str:
    s = max(1, round(seconds))
    if s < 60:
        return plural("dur.seconds", s)
    m, s = divmod(s, 60)
    return plural("dur.minutes", m) + (" " + plural("dur.seconds", s) if s else "")


def names_list(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


class ProgressEvent(BaseModel):
    seq: int
    at: datetime
    kind: Kind
    text: str
    sender: str | None = None
    draft_id: int | None = None
    done_count: int = 0
    total_count: int = 0
    finished: bool = False


class Feed:
    """In-memory event log for one run, with replay for reconnecting clients (PRG-8)."""

    def __init__(self) -> None:
        self.events: list[ProgressEvent] = []
        self.done = 0
        self.total = 0
        self.finished = False
        self.started = time.monotonic()
        self._cond = asyncio.Condition()

    def say(self, key: str, kind: Kind = "info", *, sender: str | None = None,
            draft_id: int | None = None, variant: int = 0, **values) -> ProgressEvent:
        ev = ProgressEvent(
            seq=len(self.events) + 1, at=datetime.now(), kind=kind, text=render(key, variant, **values),
            sender=sender, draft_id=draft_id, done_count=self.done, total_count=self.total, finished=self.finished,
        )
        self.events.append(ev)
        self._notify()
        return ev

    def finish(self) -> None:
        self.finished = True
        if self.events:
            self.events[-1].finished = True
        self._notify()

    def _notify(self) -> None:
        async def wake():
            async with self._cond:
                self._cond.notify_all()
        try:
            asyncio.get_running_loop().create_task(wake())
        except RuntimeError:
            pass  # no loop (sync tests): nobody can be waiting

    async def stream(self, after: int = 0) -> AsyncIterator[ProgressEvent]:
        idx = max(0, after)
        while True:
            async with self._cond:
                await self._cond.wait_for(lambda: len(self.events) > idx or self.finished)
            while idx < len(self.events):
                yield self.events[idx]
                idx += 1
            if self.finished:
                return

    @asynccontextmanager
    async def heartbeat(self, name: str):
        """PRG-5: reassure every HEARTBEAT_SECONDS while a person's step is running."""
        async def beat():
            n = 0
            while True:
                await asyncio.sleep(HEARTBEAT_SECONDS)
                self.say("still_working", "working", sender=name, variant=n, name=name)
                n += 1
        task = asyncio.create_task(beat())
        try:
            yield
        finally:
            task.cancel()
