"""Master agent: splits the chat in plain code, then runs Sorter -> Extractor -> Checker
for each sender concurrently, with no barrier between senders (INT-3..6, INT-16)."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date

from .. import db
from .. import orders as orders_mod
from ..models import DraftAction, Order
from ..progress import Feed, duration, names_list, plural
from . import checker
from .chat_parser import Message, SenderGroup, group_by_sender, is_small_talk, parse_chat
from .extractor import extract_group
from .ollama import BadOutput, HelperDown
from .sorter import sort_group

log = logging.getLogger(__name__)

FAILED_FLAG = "Couldn't read this one, please check the messages."
RUNS: dict[int, "IntakeRun"] = {}
_active: "IntakeRun | None" = None


def active_run() -> "IntakeRun | None":
    return _active if _active is not None and not _active.feed.finished else None


def start_run(db_path: str, client, model: str, sorter_model: str, text: str, user_id: int,
              today: date | None = None) -> "IntakeRun":
    """INT-6: one run at a time. A second request gets the running one back."""
    global _active
    running = active_run()
    if running is not None:
        return running
    run = IntakeRun(db_path, client, model, sorter_model, text, user_id, today)
    RUNS[run.id] = run
    _active = run
    run.task = asyncio.create_task(run.run())
    return run


class IntakeRun:
    def __init__(self, db_path, client, model, sorter_model, text, user_id, today=None):
        self.conn = db.connect(db_path)
        self.client = client
        self.model = model
        self.sorter_model = sorter_model
        self.text = text
        self.today = today or date.today()
        self.feed = Feed()
        self.task: asyncio.Task | None = None
        self.counts = {"drafts": 0, "questions": 0, "chatting": 0, "failed": 0}
        self._run_orders: list[Order] = []  # drafts made in this run, for duplicate checks
        self.helper_down = False
        self._finished: set[str] = set()
        self.id = self.conn.execute(
            "INSERT INTO intake_runs (started_by, started_at) VALUES (?, ?)", (user_id, db.now())
        ).lastrowid

    # ---------- orchestration ----------

    async def run(self) -> None:
        started = time.monotonic()
        try:
            await self._run()
        except HelperDown:
            self.feed.say("helper_down", "error")
        except Exception:
            log.exception("intake run %s failed", self.id)
            self.feed.say("run_failed", "error")
        finally:
            took = duration(time.monotonic() - started)
            parts = [plural(f"part.{k}", n) for k, n in self.counts.items() if n]
            if parts:
                self.feed.say("summary", "summary", duration=took, parts=", ".join(parts))
            else:
                self.feed.say("summary_empty", "summary", duration=took)
            self.conn.execute("UPDATE intake_runs SET finished_at = ?, summary = ? WHERE id = ?",
                              (db.now(), self.feed.events[-1].text, self.id))
            self.feed.finish()
            self.conn.close()

    async def _run(self) -> None:
        messages = parse_chat(self.text)
        fresh = [m for m in messages if not self._seen(m)]
        skipped = len(messages) - len(fresh)
        if not fresh:
            self.feed.say("nothing_new", "done")
            return
        if len(fresh) == 1:
            self.feed.say("started_one", "working")
        else:
            self.feed.say("started", "working", count=len(fresh))
        if skipped:
            self.feed.say("skipped_one" if skipped == 1 else "skipped", "info", count=skipped)

        groups = group_by_sender(fresh)
        self.feed.total = len(groups)
        names = [g.sender for g in groups]
        if len(groups) == 1:
            self.feed.say("people_one", "info", names=names[0])
        else:
            self.feed.say("people", "info", count=len(groups), names=names_list(names))

        # INT-9: a separate sorting call only pays off with a smaller model
        use_sorter = self.sorter_model != self.model and await self.client.has_model(self.sorter_model)
        if not use_sorter:
            self.feed.say("sorter_skipped", "info")

        # INT-4: every sender moves through the pipeline on their own
        await asyncio.gather(*(self._handle(g, use_sorter) for g in groups))
        if self.helper_down:
            raise HelperDown()

    # ---------- one sender ----------

    async def _handle(self, group: SenderGroup, use_sorter: bool) -> None:
        name = group.sender
        try:
            if is_small_talk(group):  # INT-8: no model call needed
                self._no_order(group, "chit_chat")
                return
            async with self.feed.heartbeat(name):
                open_orders = orders_mod.open_orders_for(self.conn, group.phone, name)
                if use_sorter:
                    sort = await sort_group(self.client, self.sorter_model, group, bool(open_orders))
                    log.info("sorter: %s -> %s (%s)", name, sort.kind, sort.reason)
                    if sort.kind in ("chit_chat", "question"):  # INT-8: no extractor call
                        self._no_order(group, sort.kind)
                        return
                    self.feed.say(f"sorted.{sort.kind}", "working", sender=name, name=name)
                else:
                    self.feed.say("reading", "working", sender=name, name=name)
                result = await extract_group(self.client, self.model, group, open_orders, self.today)
                if not result.actions and result.kind in ("chit_chat", "question"):
                    self._no_order(group, result.kind)
                else:
                    self._save_actions(group, result.actions, dict(open_orders))
        except HelperDown:
            # Leave the messages unseen so the next run picks them up again.
            self.helper_down = True
        except Exception as e:  # INT-12: this sender fails, the others carry on
            if not isinstance(e, BadOutput):
                log.exception("sender %s failed", name)
            draft_id = self._save(group, "new", None, None, [FAILED_FLAG])
            self._mark_seen(group)
            self.counts["failed"] += 1
            self._finish(group)
            self.feed.say("failed", "error", sender=name, draft_id=draft_id, name=name)
        finally:
            self._finish(group)

    def _finish(self, group: SenderGroup) -> None:
        """Count a sender as done once, before their last messages, so 'X of Y people done' is current."""
        if group.sender not in self._finished:
            self._finished.add(group.sender)
            self.feed.done += 1

    def _no_order(self, group: SenderGroup, kind: str) -> None:
        name = group.sender
        self._finish(group)
        if kind == "chit_chat":
            self.counts["chatting"] += 1
            self._mark_seen(group)
            self.feed.say("sorted.chit_chat", "done", sender=name, name=name)
        else:
            draft_id = self._save(group, "question", None, None, [])
            self._mark_seen(group)
            self.counts["questions"] += 1
            self.feed.say("sorted.question", "done", sender=name, draft_id=draft_id, name=name)

    def _save_actions(self, group: SenderGroup, actions: list[DraftAction], sender_open: dict[int, Order]) -> None:
        name = group.sender
        self._finish(group)
        if not actions:
            self.feed.say("draft.none", "done", sender=name, name=name)
            self._mark_seen(group)
            return
        all_open = orders_mod.all_open_orders(self.conn)
        for a in actions:
            others = [o for oid, o in all_open if oid != a.target_order_id] + self._run_orders
            flags = checker.check(a, sender_open, others, self.today)
            draft_id = self._save(group, a.action, a.order, a.target_order_id, flags)
            if a.order is not None:
                self._run_orders.append(a.order)
            self.counts["drafts"] += 1
            self.feed.say(f"draft.{a.action}", "done", sender=name, draft_id=draft_id, name=name)
            for f in flags:
                self.feed.say("flag", "warn", sender=name, name=name, flag=f)
        self._mark_seen(group)  # only after the drafts are stored, so a crash loses nothing

    def _save(self, group: SenderGroup, action: str, order: Order | None, target: int | None,
              flags: list[str]) -> int:
        return orders_mod.save_draft(
            self.conn, source="chat", action=action, order=order, target_order_id=target, run_id=self.id,
            sender=group.sender, flags=flags, raw_text=group.as_text(),
        )

    # ---------- seen messages (INT-3) ----------

    def _seen(self, m: Message) -> bool:
        return self.conn.execute("SELECT 1 FROM seen_messages WHERE hash = ?", (m.key(),)).fetchone() is not None

    def _mark_seen(self, group: SenderGroup) -> None:
        self.conn.executemany(
            "INSERT OR IGNORE INTO seen_messages (hash, run_id, sender, sent_at) VALUES (?, ?, ?, ?)",
            [(m.key(), self.id, m.sender, m.sent_at.isoformat() if m.sent_at else None) for m in group.messages],
        )
