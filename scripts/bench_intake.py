"""INT-20: time the old single-call extraction against the multi-agent pipeline
on a sample chat, using the real local model.

    python scripts/bench_intake.py [samples/sample_chat.txt]

Uses a throwaway database, so your real orders aren't touched."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from order_taker import db  # noqa: E402
from order_taker.agents import master  # noqa: E402
from order_taker.agents.ollama import OllamaClient  # noqa: E402
from order_taker.config import get_settings  # noqa: E402
from order_taker.extract import extract_orders  # noqa: E402


async def run_pipeline(text: str, db_path: str) -> tuple[float, float, int]:
    s = get_settings()
    client = OllamaClient(s.ollama_url, s.parallel)
    conn = db.connect(db_path)
    db.migrate(conn)
    uid = conn.execute(
        "INSERT INTO users (role, username, name, pin_hash, created_at) VALUES ('admin', 'bench', 'Bench', 'x', ?)",
        (db.now(),),
    ).lastrowid
    conn.close()
    t0 = time.perf_counter()
    run = master.start_run(db_path, client, s.model, s.sorter_model, text, uid)
    first_draft = None
    async for ev in run.feed.stream():
        if ev.draft_id and first_draft is None:
            first_draft = time.perf_counter() - t0
        print("   ", ev.text)
    await run.task
    return time.perf_counter() - t0, first_draft or 0.0, run.counts["drafts"]


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "samples/sample_chat.txt"
    text = Path(path).read_text(encoding="utf-8")
    s = get_settings()
    print(f"Chat: {path}\nModels: extractor={s.model} sorter={s.sorter_model} parallel={s.parallel}\n")

    # warm the main model so neither side pays the load time
    extract_orders("[01/01/26, 9:00 AM] Warmup: 1 cake tomorrow")

    print("Old: one call for the whole chat…")
    t0 = time.perf_counter()
    old = extract_orders(text)
    old_s = time.perf_counter() - t0
    print(f"    {len(old)} orders in {old_s:.1f}s\n")

    print("New: multi-agent pipeline…")
    with tempfile.TemporaryDirectory() as tmp:
        total, first, n = asyncio.run(run_pipeline(text, os.path.join(tmp, "bench.db")))
    print(f"    {n} drafts in {total:.1f}s (first draft ready after {first:.1f}s)\n")
    print(f"Old {old_s:.1f}s  vs  New {total:.1f}s total, {first:.1f}s to first draft")


if __name__ == "__main__":
    main()
