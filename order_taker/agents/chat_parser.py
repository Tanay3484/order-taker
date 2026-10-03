"""Parse WhatsApp exports into messages and group them by sender (INT-1, INT-2).
Plain code, no model: instant and predictable."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime

from pydantic import BaseModel

from ..auth import normalise_phone

_INVISIBLE = dict.fromkeys(map(ord, "‎‏﻿‪‬"), None)
_DATE = r"(\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})"
_TIME = r"(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AaPp]\.?\s?[Mm]\.?)?)"
IOS = re.compile(rf"^\[{_DATE},?\s+{_TIME}\]\s*(.*)$")
ANDROID = re.compile(rf"^{_DATE},?\s+{_TIME}\s*[-–]\s*(.*)$")
SENDER = re.compile(r"^([^:]{1,60}?):\s?(.*)$", re.S)

SYSTEM_TEXT = re.compile(
    r"^(<media omitted>|<attached:.*>|(image|video|audio|sticker|gif|document) omitted|"
    r"this message was deleted|you deleted this message|null|missed (voice|video) call)$",
    re.I,
)


class Message(BaseModel):
    sent_at: datetime | None
    sender: str
    text: str

    def key(self) -> str:
        """INT-3: same sender + time + text = same message."""
        stamp = self.sent_at.isoformat() if self.sent_at else ""
        return hashlib.sha256(f"{stamp}|{self.sender}|{self.text}".encode()).hexdigest()


class SenderGroup(BaseModel):
    sender: str
    phone: str | None
    messages: list[Message]

    def as_text(self) -> str:
        lines = []
        for m in self.messages:
            stamp = m.sent_at.strftime("%a %d %b, %I:%M %p") if m.sent_at else ""
            lines.append(f"[{stamp}] {m.text}" if stamp else m.text)
        return "\n".join(lines)


def _parse_stamp(d: str, t: str) -> datetime | None:
    d = re.sub(r"[.-]", "/", d)
    t = re.sub(r"\s+", " ", t.replace(".", "")).strip().upper()
    has_ampm = t.endswith(("AM", "PM"))
    t = re.sub(r"\s*(AM|PM)$", r" \1", t)
    year = "%y" if len(d.split("/")[-1]) == 2 else "%Y"
    tfmt = ("%I:%M:%S %p" if t.count(":") == 2 else "%I:%M %p") if has_ampm else (
        "%H:%M:%S" if t.count(":") == 2 else "%H:%M")
    for dfmt in (f"%d/%m/{year}", f"%m/%d/{year}"):  # India is day-first; fall back for US exports
        try:
            return datetime.strptime(f"{d} {t}", f"{dfmt} {tfmt}")
        except ValueError:
            continue
    return None


def parse_chat(text: str) -> list[Message]:
    messages: list[Message] = []
    current: Message | None = None
    saw_header = False

    def flush():
        nonlocal current
        if current is not None:
            body = current.text.replace("<This message was edited>", "").strip()
            if body and not SYSTEM_TEXT.match(body):
                messages.append(current.model_copy(update={"text": body}))
        current = None

    for raw in (text or "").splitlines():
        line = raw.translate(_INVISIBLE).replace(" ", " ").replace(" ", " ").rstrip()
        m = IOS.match(line) or ANDROID.match(line)
        if m:
            saw_header = True
            flush()
            stamp = _parse_stamp(m.group(1), m.group(2))
            rest = m.group(3)
            s = SENDER.match(rest)
            if s is None:
                continue  # system line without a sender ("Messages are end-to-end encrypted", "X added Y")
            current = Message(sent_at=stamp, sender=s.group(1).strip(), text=s.group(2))
        elif current is not None:
            current.text += "\n" + line  # multi-line message
    flush()

    if not saw_header:  # INT-2: no timestamps, treat it all as one unknown sender
        body = (text or "").strip()
        return [Message(sent_at=None, sender="Unknown sender", text=body)] if body else []
    return messages


SMALL_TALK = set("""
hi hii hiii hello helo hey heyy hlo good morning night evening afternoon gm gn ge tc take care
thanks thank thankyou thanku thx ty tq tysm so much very you u ok okay okk k kk sure fine great nice super
welcome bye byee see soon later sweet dreams have a nice day lovely wonderful awesome
namaste namaskara vanakkam ram jai shri sat sri akal salaam
aunty auntie uncle ji bhaiya bhaiyya bhai didi di akka anna amma appa dear sis bro madam maam mam sir
dhanyavad dhanyavaad shukriya nanri nandri dhanyavadagalu bahut accha acha theek hai haan ha
""".split())


def is_small_talk(group: SenderGroup) -> bool:
    """INT-8: greetings and thanks only, no numbers. Strict on purpose: one unknown word and the model decides."""
    text = " ".join(m.text for m in group.messages).lower()
    if re.search(r"\d", text):
        return False
    words = re.findall(r"[a-z']+", text.replace("'", ""))
    return bool(words) and all(w in SMALL_TALK for w in words)


def _phone_from_sender(sender: str) -> str | None:
    """Unsaved contacts show as '+91 98450 12345'."""
    if re.fullmatch(r"[+\d][\d\s()-]{6,}", sender):
        return normalise_phone(sender)
    return None


def group_by_sender(messages: list[Message]) -> list[SenderGroup]:
    groups: dict[str, SenderGroup] = {}
    for m in messages:
        g = groups.get(m.sender)
        if g is None:
            g = groups[m.sender] = SenderGroup(sender=m.sender, phone=_phone_from_sender(m.sender), messages=[])
        g.messages.append(m)
    return list(groups.values())
