"""004 Live progress feed."""

import json
import re
from pathlib import Path

import pytest

from order_taker import progress

from .conftest import login_customer, make_customer, page_text, post, setup_admin, wait_for_run
from .test_intake import SAMPLE, run_intake, sample_fake

AGENTS = Path(__file__).resolve().parent.parent / "order_taker" / "agents"
BANNED = ["ollama", "json", "api", "agent", "token", "model", "qwen", "llama", "error code", "traceback",
          "exception", "schema", "prompt", "http"]
SAMPLE_VALUES = dict(count=4, names="Priya, Rahul and Sneha", name="Priya", flag="There's no delivery date yet.",
                     duration="41 seconds", parts="3 things to check", n=3)


def all_rendered() -> list[str]:
    out = []
    for key, options in progress.TEMPLATES.items():
        for i in range(len(options)):
            out.append(progress.render(key, i, **SAMPLE_VALUES))
    return out


def test_prg3_prg4_templates_are_plain_english():
    """PRG-3, PRG-4: no technical words in any template."""
    for text in all_rendered():
        words = re.findall(r"[a-z]+", text.lower())
        for bad in BANNED:
            if " " in bad:
                assert bad not in text.lower(), text
            else:
                assert bad not in words, f"{bad!r} in {text!r}"


def test_prg3_agents_only_use_known_template_keys():
    """PRG-3: agents pass template keys, never their own sentences."""
    used = set()
    for py in AGENTS.glob("*.py"):
        src = py.read_text(encoding="utf-8")
        used |= set(re.findall(r'say\(\s*"([^"]+)"', src))
        for prefix in re.findall(r'say\(\s*f"([a-z_]+\.)\{', src):
            used |= {k for k in progress.TEMPLATES if k.startswith(prefix)}
        assert not re.search(r"say\(\s*'", src)
    assert used and used <= set(progress.TEMPLATES)
    for kind in ("new_order", "change", "cancel", "question", "chit_chat"):
        assert f"sorted.{kind}" in progress.TEMPLATES
    for action in ("new", "update", "cancel"):
        assert f"draft.{action}" in progress.TEMPLATES


def test_prg3_unknown_key_is_an_error():
    with pytest.raises(KeyError):
        progress.render("made up text")


async def test_prg2_prg6_prg7_sample_run_narrates_each_step(app, settings):
    """PRG-2, PRG-6, PRG-7: every step is narrated; counts and summary are right."""
    run = await run_intake(settings, sample_fake())
    texts = [e.text for e in run.feed.events]
    assert texts[0] == "Got it! Reading 6 new messages…"
    assert "Found messages from 4 people: Priya, Rahul Bhaiya, Meena and Sneha." in texts
    assert "Meena is just chatting. Nothing to order." in texts
    assert "Priya wants to order something. Writing down the details…" in texts
    assert "Priya's order is ready for you to check." in texts
    assert "Something to check on Priya's order: Delivery or pickup? No address was given." in texts
    last = run.feed.events[-1]
    assert last.kind == "summary" and last.finished
    assert re.fullmatch(r"All done in \d+ seconds?: 3 things to check, 1 just chatting\.", last.text)
    assert last.done_count == last.total_count == 4
    assert any(e.draft_id for e in run.feed.events)


async def test_prg5_heartbeat_reassures_when_slow(app, settings, monkeypatch):
    """PRG-5: 'still working' messages appear while a step is slow, with varied wording."""
    monkeypatch.setattr(progress, "HEARTBEAT_SECONDS", 0.05)
    fake = sample_fake()
    fake.delays = {"Priya": 0.3}
    run = await run_intake(settings, fake)
    beats = [e.text for e in run.feed.events if e.sender == "Priya" and ("Still" in e.text or "longer" in e.text)]
    assert len(beats) >= 2 and len(set(beats)) >= 2


def test_prg_duration_and_plurals():
    assert progress.duration(1) == "1 second"
    assert progress.duration(38.4) == "38 seconds"
    assert progress.duration(65) == "1 minute 5 seconds"
    assert progress.duration(120) == "2 minutes"
    assert progress.plural("part.drafts", 1) == "1 thing to check"


def _sse_events(text: str) -> list[dict]:
    return [json.loads(m) for m in re.findall(r"event: progress\ndata: (.+)\n", text)]


def test_prg1_prg8_sse_stream_and_replay(client, app):
    """PRG-1, PRG-8: the page subscribes to a live stream; reconnecting replays what was missed."""
    fake = app.state.ollama
    fake.sorts, fake.extracts = sample_fake().sorts, sample_fake().extracts
    setup_admin(client)
    r = post(client, "/admin/intake", {"text": SAMPLE}, page="/admin/intake")
    run_id = int(r.headers["location"].split("run=")[1])
    page = client.get(r.headers["location"]).text
    assert 'aria-live="polite"' in page and f'data-run="{run_id}"' in page
    wait_for_run(run_id)

    full = _sse_events(client.get(f"/admin/intake/{run_id}/events").text)
    assert [e["seq"] for e in full] == list(range(1, len(full) + 1))
    replay = _sse_events(client.get(f"/admin/intake/{run_id}/events", headers={"Last-Event-ID": "3"}).text)
    assert [e["seq"] for e in replay] == list(range(4, len(full) + 1))


def test_prg8_after_restart_shows_saved_summary(client, app, conn):
    """PRG-8: the summary survives a server restart."""
    setup_admin(client)
    conn.execute("INSERT INTO intake_runs (started_at, finished_at, summary) VALUES ('x', 'y', 'All done in 9 seconds.')")
    run_id = conn.execute("SELECT MAX(id) FROM intake_runs").fetchone()[0]
    events = _sse_events(client.get(f"/admin/intake/{run_id}/events").text)
    assert events[0]["text"] == "All done in 9 seconds." and events[0]["finished"]
    assert "Last time: All done in 9 seconds." in page_text(client.get("/admin/intake"))


def test_prg9_progress_box_is_accessible():
    """PRG-9: polite live region; icons hidden from screen readers."""
    tpl = (AGENTS.parent / "web" / "templates" / "admin_intake.html").read_text(encoding="utf-8")
    js = (AGENTS.parent / "web" / "static" / "progress.js").read_text(encoding="utf-8")
    assert 'aria-live="polite"' in tpl
    assert 'setAttribute("aria-hidden", "true")' in js


def test_prg10_customers_cannot_see_the_feed(client, conn):
    """PRG-10."""
    setup_admin(client)
    conn.execute("INSERT INTO intake_runs (started_at, summary) VALUES ('x', '')")
    client.cookies.clear()
    make_customer(conn)
    login_customer(client)
    assert client.get("/admin/intake/1/events").status_code == 403


async def test_prg6_people_done_counter_is_current(app, settings):
    """PRG-6: a sender's 'ready' message already counts them as done."""
    run = await run_intake(settings, sample_fake())
    ready = [e for e in run.feed.events if e.text.endswith("is ready for you to check.")
             or e.text.endswith("Nothing to order.")]
    assert sorted(e.done_count for e in ready) == [1, 2, 3, 4]
