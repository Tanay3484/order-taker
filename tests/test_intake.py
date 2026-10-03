"""003 Multi-agent intake, driven through the real pipeline with FakeOllama."""

import json
import time
from datetime import date

from order_taker import db
from order_taker import orders as om
from order_taker.agents import master

from .conftest import (FakeOllama, get_csrf, make_customer, make_order, new_action, page_text, post, setup_admin,
                       wait_for_run)

TODAY = date(2026, 10, 2)
SAMPLE = """[02/10/26, 9:14 PM] Priya: Hi aunty! 1 kg chocolate truffle cake for Sunday evening? Eggless please
[02/10/26, 9:15 PM] Priya: Write "Happy Birthday Arjun" on it
[02/10/26, 9:30 PM] Rahul Bhaiya: 2 box brownies kal subah, address 14B Lakeview Apts
[02/10/26, 9:31 PM] Rahul Bhaiya: sorry make it 3 boxes
[02/10/26, 10:02 PM] Meena: Good night aunty
[02/10/26, 10:05 PM] Sneha: 12 cupcakes vanilla, Saturday 4pm pickup. My number 98450 12345"""


def sample_fake(**kw) -> FakeOllama:
    fake = FakeOllama(**kw)
    fake.sorts = {"Meena": "chit_chat"}
    fake.extracts = {
        "Priya": {"actions": [new_action("Priya", [("chocolate truffle cake", 1, "kg")], delivery_date="2026-10-04",
                                         notes="Eggless; Happy Birthday Arjun")]},
        "Rahul Bhaiya": {"actions": [new_action("Rahul Bhaiya", [("brownies", 3, "box")], delivery_date="2026-10-03",
                                                address="14B Lakeview Apts")]},
        "Sneha": {"actions": [new_action("Sneha", [("vanilla cupcakes", 12, "pcs")], delivery_date="2026-10-03",
                                         delivery_time="4pm pickup", phone="98450 12345")]},
    }
    return fake


async def run_intake(settings, fake, text=SAMPLE, uid=None):
    run = master.start_run(settings.db_path, fake, settings.model, settings.sorter_model, text, uid, today=TODAY)
    await run.task
    return run


def drafts(settings):
    conn = db.connect(settings.db_path)
    rows = conn.execute("SELECT * FROM drafts ORDER BY id").fetchall()
    conn.close()
    return rows


async def test_int4_int8_sample_chat_end_to_end(app, settings):
    """INT-4, INT-7, INT-8: chit-chat skips the extractor; each sender gets their own draft."""
    fake = sample_fake()
    run = await run_intake(settings, fake)
    assert {c["sender"] for c in fake.extract_calls()} == {"Priya", "Rahul Bhaiya", "Sneha"}
    assert [d["sender"] for d in drafts(settings)] == ["Priya", "Rahul Bhaiya", "Sneha"] or \
        sorted(d["sender"] for d in drafts(settings)) == ["Priya", "Rahul Bhaiya", "Sneha"]
    assert run.counts == {"drafts": 3, "questions": 0, "chatting": 1, "failed": 0}


async def test_int10_extractor_only_sees_its_sender(app, settings):
    """INT-10: each extractor gets one person's messages, with when they were sent."""
    fake = sample_fake()
    await run_intake(settings, fake)
    priya = fake.extract_calls("Priya")[0]
    assert "chocolate truffle" in priya["user"] and "brownies" not in priya["user"]
    assert "Fri 02 Oct, 09:14 PM" in priya["user"]  # when each message was sent


async def test_int3_second_run_skips_seen_messages(app, settings):
    """INT-3."""
    fake = sample_fake()
    await run_intake(settings, fake)
    master._active = None
    calls_before = len(fake.calls)
    extra = SAMPLE + "\n[03/10/26, 8:00 AM] Divya: 1 kg cheesecake for Monday"
    run = await run_intake(settings, fake, extra)
    new_senders = {c["sender"] for c in fake.calls[calls_before:]}
    assert new_senders == {"Divya"}
    texts = [e.text for e in run.feed.events]
    assert "Skipped 6 messages I've already gone through before." in texts


async def test_int3_nothing_new(app, settings):
    fake = sample_fake()
    await run_intake(settings, fake)
    master._active = None
    run = await run_intake(settings, fake)
    assert run.feed.events[0].text.startswith("There's nothing new here.")


async def test_int5_int19_runs_in_parallel_within_limit(app, settings):
    """INT-5, INT-19: 3 senders with a 0.2s model finish in < 2.5x one sender's time; never above the limit."""
    one_sender = 2 * 0.2  # sort + extract
    fake = sample_fake(parallel=3, delay=0.2)
    fake.sorts = {}
    text = "\n".join(line for line in SAMPLE.splitlines() if "Meena" not in line)
    t0 = time.perf_counter()
    await run_intake(settings, fake, text)
    took = time.perf_counter() - t0
    assert took < 2.5 * one_sender, took
    assert fake.max_in_flight == 3


async def test_int5_limit_of_one_is_respected(app, settings):
    fake = sample_fake(parallel=1, delay=0.01)
    await run_intake(settings, fake)
    assert fake.max_in_flight == 1


async def test_int6_one_run_at_a_time(app, settings):
    """INT-6."""
    fake = sample_fake(delay=0.05)
    a = master.start_run(settings.db_path, fake, settings.model, settings.sorter_model, SAMPLE, None, today=TODAY)
    b = master.start_run(settings.db_path, fake, settings.model, settings.sorter_model, "other", None, today=TODAY)
    assert a is b
    await a.task


async def test_int8_question_becomes_needs_reply(app, settings):
    """INT-8: questions skip the extractor and become a note for the admin."""
    fake = FakeOllama()
    fake.sorts = {"Arjun": "question"}
    run = await run_intake(settings, fake, "[03/10/26, 9:02 AM] Arjun: How much is red velvet per kg?")
    (d,) = drafts(settings)
    assert d["action"] == "question" and "red velvet" in d["raw_text"]
    assert fake.extract_calls() == []
    assert run.counts["questions"] == 1


async def test_int9_no_small_sorter_means_one_call_per_sender(app, settings):
    """INT-9 (amended): without a smaller sorter model, the extractor classifies in the same call."""
    fake = sample_fake()
    fake.models = {"qwen2.5:7b"}
    run = await run_intake(settings, fake)
    assert not any(c["sort"] for c in fake.calls)
    assert len(fake.calls) == 3  # one per sender; Meena's "Good night" needs no call
    assert {c["model"] for c in fake.calls} == {"qwen2.5:7b"}
    assert "Reading each person's messages in one go." in [e.text for e in run.feed.events]
    assert run.counts == {"drafts": 3, "questions": 0, "chatting": 1, "failed": 0}


async def test_int9_same_model_configured_skips_sorter(app, settings):
    fake = sample_fake()
    run = master.start_run(settings.db_path, fake, "qwen2.5:7b", "qwen2.5:7b", SAMPLE, None, today=TODAY)
    await run.task
    assert not any(c["sort"] for c in fake.calls)


async def test_int9_question_found_by_extractor(app, settings):
    fake = FakeOllama()
    fake.models = {"qwen2.5:7b"}
    fake.sorts = {"Arjun": "question"}
    run = await run_intake(settings, fake, "[03/10/26, 9:02 AM] Arjun: How much is red velvet per kg?")
    assert run.counts["questions"] == 1 and drafts(settings)[0]["action"] == "question"


async def test_int21_int22_dates_and_phone_finished_in_code(app, settings):
    """INT-21, INT-22: 'Sunday' becomes a date from the message's day; a phone in the text is used."""
    fake = FakeOllama()
    fake.extracts = {"Sneha": {"actions": [new_action("Sneha", [("cupcakes", 12, "pcs")], delivery_date="Sunday")]}}
    await run_intake(settings, fake, "[02/10/26, 10:05 PM] Sneha: 12 cupcakes Sunday pickup. My number 98450 12345")
    order = json.loads(drafts(settings)[0]["payload_json"])
    assert order["delivery_date"] == "2026-10-04"  # 2 Oct 2026 is a Friday
    assert order["phone"] == "9845012345"


async def test_int10_int11_change_to_existing_order(app, settings, conn):
    """INT-10, INT-11: open orders reach the prompt; an update draft points at the order."""
    rahul = make_customer(conn, "Rahul Bhaiya", "9900011122")
    oid = make_order(conn, rahul, items=(("brownies", 2, "box"),), delivery_date="2026-10-03")
    fake = FakeOllama()
    fake.sorts = {"+91 99000 11122": "change"}
    upd = new_action("Rahul Bhaiya", [("brownies", 3, "box")], delivery_date="2026-10-03", address="14B")
    upd.update(action="update", target_order_id=oid)
    fake.extracts = {"+91 99000 11122": {"actions": [upd]}}
    await run_intake(settings, fake, "[02/10/26, 9:31 PM] +91 99000 11122: make it 3 boxes")
    assert f"#{oid}: 2 box brownies" in fake.extract_calls()[0]["user"]
    (d,) = drafts(settings)
    assert d["action"] == "update" and d["target_order_id"] == oid
    assert "points to an order" not in d["flags_json"]


async def test_int12_bad_output_retried_once(app, settings):
    """INT-12: one bad answer is retried."""
    fake = sample_fake()
    fake.bad = {"Priya": 1}
    run = await run_intake(settings, fake)
    assert len(fake.extract_calls("Priya")) == 2
    assert run.counts["failed"] == 0


async def test_int12_bad_output_twice_flags_and_others_continue(app, settings):
    """INT-12: after two bad answers the draft is flagged with the original messages; others carry on."""
    fake = sample_fake()
    fake.bad = {"Priya": 2}
    run = await run_intake(settings, fake)
    rows = drafts(settings)
    priya = next(d for d in rows if d["sender"] == "Priya")
    assert "Couldn't read this one" in priya["flags_json"] and "chocolate truffle" in priya["raw_text"]
    assert run.counts == {"drafts": 2, "questions": 0, "chatting": 1, "failed": 1}
    assert any(e.text.startswith("I couldn't make sense of Priya's messages") for e in run.feed.events)


async def test_int12_helper_down_leaves_messages_unseen(app, settings):
    fake = sample_fake()
    fake.up = False
    run = await run_intake(settings, fake)
    assert any(e.kind == "error" for e in run.feed.events)
    conn = db.connect(settings.db_path)
    assert conn.execute("SELECT COUNT(*) FROM seen_messages").fetchone()[0] == 0


async def test_int14_checker_flags_saved_on_drafts(app, settings):
    """INT-14: flags are stored with the draft."""
    fake = sample_fake()
    await run_intake(settings, fake)
    priya = next(d for d in drafts(settings) if d["sender"] == "Priya")
    flags = json.loads(priya["flags_json"])
    assert "There's no phone number, so the customer can't track this order." in flags
    assert "Delivery or pickup? No address was given." in flags


async def test_int16_drafts_appear_before_run_ends(app, settings):
    """INT-16: a fast sender's draft is ready while a slow one is still working."""
    fake = sample_fake(delay=0.01)
    fake.delays = {"Priya": 0.5}
    run = master.start_run(settings.db_path, fake, settings.model, settings.sorter_model, SAMPLE, None, today=TODAY)
    async for ev in run.feed.stream():
        if ev.draft_id:
            assert not run.feed.finished
            break
    await run.task


async def test_int18_nothing_changes_until_accepted(app, settings):
    """INT-18."""
    await run_intake(settings, sample_fake())
    conn = db.connect(settings.db_path)
    assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_int16_int17_web_flow(client, app, settings, conn):
    """INT-16, INT-17: start from the page, drafts show up, accept / edit / discard."""
    fake = app.state.ollama
    fake.sorts = sample_fake().sorts
    fake.extracts = sample_fake().extracts
    setup_admin(client)
    r = post(client, "/admin/intake", {"text": SAMPLE}, page="/admin/intake")
    assert r.status_code == 303
    run_id = int(r.headers["location"].split("run=")[1])
    wait_for_run(run_id)
    page = page_text(client.get(f"/admin/intake?run={run_id}"))
    assert "What's happening" in page
    for name in ("Priya", "Rahul Bhaiya", "Sneha"):
        assert name in page
    ids = {d["sender"]: d["id"] for d in conn.execute("SELECT * FROM drafts")}

    # fetch one card the way the page script does
    assert "Accept" in client.get(f"/admin/drafts/{ids['Priya']}/card").text

    # Accept as is (Sneha has a phone -> PIN page)
    r = post(client, f"/admin/drafts/{ids['Sneha']}/accept", page="/admin/intake")
    assert "PIN" in r.text

    # Edit, then accept
    token = get_csrf(client, f"/admin/drafts/{ids['Rahul Bhaiya']}/edit")
    r = client.post(f"/admin/drafts/{ids['Rahul Bhaiya']}/edit", data={
        "csrf": token, "customer": "Rahul", "phone": "", "item_name": ["brownies"], "item_qty": ["4"],
        "item_unit": ["box"], "delivery_date": "2026-10-03", "delivery_time": "", "address": "14B", "notes": "",
    }, follow_redirects=False)
    assert r.status_code == 200  # no phone -> explains it can't be tracked
    rahul = conn.execute("SELECT * FROM orders WHERE customer_name = 'Rahul'").fetchone()
    assert om.items_text(om.get_items(conn, rahul["id"])) == "4 box brownies"

    # Discard
    post(client, f"/admin/drafts/{ids['Priya']}/discard", page="/admin/intake")
    assert om.get_draft(conn, ids["Priya"])["state"] == "discarded"


def test_int17_update_draft_shows_old_to_new(client, conn):
    """INT-17: update drafts show what changes."""
    setup_admin(client)
    rahul = make_customer(conn, "Rahul", "9900011122")
    oid = make_order(conn, rahul, items=(("brownies", 2, "box"),))
    current = om.to_model(conn, om.get_order(conn, oid))
    new = current.model_copy(update={"items": [current.items[0].model_copy(update={"quantity": 3})]})
    om.save_draft(conn, source="chat", action="update", order=new, target_order_id=oid, sender="Rahul")
    page = page_text(client.get("/admin/intake"))
    assert "2 box brownies" in page and "3 box brownies" in page and "Item changed" in page


def test_int17_cancel_draft_cancels_order(client, conn):
    setup_admin(client)
    oid = make_order(conn, make_customer(conn))
    d = om.save_draft(conn, source="chat", action="cancel", order=None, target_order_id=oid, sender="Priya")
    post(client, f"/admin/drafts/{d}/accept", page="/admin/intake")
    assert om.get_order(conn, oid)["status"] == "cancelled"


def test_int6_page_shows_running_run(client, app, settings):
    setup_admin(client)
    fake = app.state.ollama
    fake.delay = 0.3
    post(client, "/admin/intake", {"text": SAMPLE}, page="/admin/intake")
    page = page_text(client.get("/admin/intake"))
    assert "still working on the last batch" in page
    wait_for_run(max(master.RUNS))


async def test_int11_update_of_unknown_order_becomes_new(app, settings):
    """INT-11: an 'update' pointing at an order this sender doesn't have is treated as a new order."""
    fake = FakeOllama()
    bogus = new_action("Rahul", [("brownies", 3, "box")], delivery_date="kal", address="14B")
    bogus.update(action="update", target_order_id=1)
    fake.extracts = {"Rahul": {"actions": [bogus]}}
    chat = "[02/10/26, 9:30 PM] Rahul: 2 box brownies kal\n[02/10/26, 9:31 PM] Rahul: make it 3"
    await run_intake(settings, fake, chat)
    (d,) = drafts(settings)
    assert d["action"] == "new" and d["target_order_id"] is None


def test_strict_schema_requires_every_field():
    """Models skip optional fields under structured output, so every field is asked for."""
    from order_taker.agents.ollama import strict_schema
    from order_taker.models import ExtractResult
    js = strict_schema(ExtractResult)
    assert set(js["required"]) == {"kind", "actions"}
    assert "unit" in js["$defs"]["OrderItem"]["required"]
    assert "notes" in js["$defs"]["Order"]["required"]


async def test_extractor_system_prompt_is_the_same_for_everyone(app, settings):
    """Per-sender details live in the user message so Ollama can reuse the cached system prompt."""
    fake = sample_fake()
    await run_intake(settings, fake)
    assert len({c["system"] for c in fake.extract_calls()}) == 1


async def test_int8_small_talk_needs_no_model_call(app, settings):
    """INT-8: greetings only -> chit-chat in code."""
    fake = FakeOllama()
    chat = ("[02/10/26, 10:02 PM] Meena: Good night aunty \U0001F60A\n"
            "[02/10/26, 10:03 PM] Meena: Thank you so much ji \U0001F64F")
    run = await run_intake(settings, fake, chat)
    assert fake.calls == [] and run.counts["chatting"] == 1
