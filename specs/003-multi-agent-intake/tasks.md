# 003 Multi-Agent Order Intake: Tasks

- [x] T1. `agents/chat_parser.py` + tests; extend `samples/` with an Android-format chat and a multi-line message (INT-1, INT-2)
- [x] T2. `agents/ollama.py` async client: schema, timeout, one retry, semaphore hook (INT-5, INT-12)
- [x] T3. `agents/sorter.py` + fallback when sorter model missing (INT-7, INT-8, INT-9)
- [x] T4. `agents/extractor.py`: per-sender prompt incl. open orders, `DraftAction` schema (INT-10, INT-11, INT-13)
- [x] T5. `agents/checker.py` pure rules + tests per flag (INT-14, INT-15)
- [x] T6. `agents/master.py` `IntakeRun`: seen-message dedupe, per-sender tasks, single-run lock, drafts persisted incrementally (INT-3, INT-4, INT-6, INT-16)
- [x] T7. Concurrency test with delayed fake model (INT-19)
- [x] T8. Admin intake page: paste/upload, draft cards with Accept / Edit / Discard, old→new diff for updates (INT-16, INT-17, INT-18)
- [x] T9. `scripts/bench_intake.py` comparing old vs new (INT-20)
- [x] T10. README: Ollama tuning section (`OLLAMA_NUM_PARALLEL`, low-RAM advice)
- [x] T11. `agents/dates.py` resolver + extractor post-processing for dates and phones (INT-21, INT-22)
- [x] T12. Extractor also returns `kind`; master skips the sorter when there's no smaller model (INT-9 amended)
