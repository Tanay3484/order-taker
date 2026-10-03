"""003 INT-1, INT-2: parsing WhatsApp exports."""

from datetime import datetime
from pathlib import Path

import pytest

from order_taker.agents.chat_parser import group_by_sender, is_small_talk, parse_chat

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def test_int1_ios_format():
    msgs = parse_chat((SAMPLES / "sample_chat.txt").read_text(encoding="utf-8"))
    assert [m.sender for m in msgs] == ["Priya", "Priya", "Rahul Bhaiya", "Rahul Bhaiya", "Meena", "Sneha"]
    assert msgs[0].sent_at == datetime(2026, 10, 2, 21, 14)


def test_int1_android_format_multiline_and_system_lines():
    msgs = parse_chat((SAMPLES / "sample_chat_android.txt").read_text(encoding="utf-8"))
    senders = [m.sender for m in msgs]
    assert "Messages and calls are end-to-end encrypted" not in " ".join(m.text for m in msgs)
    assert all("omitted" not in m.text.lower() for m in msgs)
    multi = next(m for m in msgs if m.sender == "Kavya")
    assert "\n" in multi.text and "less sugar" in multi.text
    assert "+91 99001 23456" in senders
    assert msgs[0].sent_at == datetime(2026, 10, 3, 8, 5)


def test_int1_edited_marker_removed_and_invisible_chars_ignored():
    text = "‎[03/10/26, 9:00 AM] Anu: 2 brownies <This message was edited>"
    (m,) = parse_chat(text)
    assert m.sender == "Anu" and m.text == "2 brownies"


def test_int2_no_timestamps_is_one_unknown_sender():
    msgs = parse_chat("hi aunty 2 cakes for sunday\nthanks!")
    assert len(msgs) == 1 and msgs[0].sender == "Unknown sender" and msgs[0].sent_at is None
    assert parse_chat("   ") == []


def test_int3_message_key_is_stable():
    a = parse_chat("[02/10/26, 9:14 PM] Priya: 1 cake")[0]
    b = parse_chat("[02/10/26, 9:14 PM] Priya: 1 cake")[0]
    c = parse_chat("[02/10/26, 9:15 PM] Priya: 1 cake")[0]
    assert a.key() == b.key() != c.key()


def test_int4_grouping_and_phone_from_unsaved_contact():
    msgs = parse_chat("[02/10/26, 9:14 PM] +91 98450 12345: 1 cake\n[02/10/26, 9:15 PM] Priya: hi")
    groups = group_by_sender(msgs)
    assert [(g.sender, g.phone) for g in groups] == [("+91 98450 12345", "9845012345"), ("Priya", None)]


@pytest.mark.parametrize("text, small", [
    ("Good night aunty \U0001F60A", True),
    ("Thank you so much ji \U0001F64F", True),
    ("ok", True),
    ("Hi aunty! Can I get a cake?", False),
    ("Thanks, 2 more please", False),
    ("good morning, cake ready?", False),
])
def test_int8_small_talk_is_strict(text, small):
    """INT-8: only greetings/thanks with no numbers count as small talk."""
    (g,) = group_by_sender(parse_chat(f"[02/10/26, 9:00 PM] Meena: {text}"))
    assert is_small_talk(g) is small
