# 003 Multi-Agent Order Intake: Design

Status: Implemented

## Pipeline
```
paste / upload
     │
     ▼
Master (plain code, instant)
  parse → drop system lines → drop already-seen → group by sender
     │
     │  one asyncio task per sender (no barrier between stages)
     ├──▶ [Sorter 3b] ─▶ [Extractor 7b] ─▶ [Checker code] ─▶ draft ready ─▶ UI
     ├──▶ [Sorter 3b] ─▶ chit_chat ─▶ skipped
     └──▶ [Sorter 3b] ─▶ [Extractor 7b] ─▶ [Checker code] ─▶ draft ready ─▶ UI
                       ▲
          shared asyncio.Semaphore(ORDER_PARALLEL) around every model call
```
Why it's faster than the single call:
1. **Less to read.** Each extractor only sees one person's messages, and messages already handled are never sent again (INT-3). Long contexts are the main cost on a local model.
2. **Chit-chat is cheap.** The 3B sorter answers in a short JSON and skips the 7B call completely.
3. **Overlapping work.** With Ollama's parallel slots, several senders are processed together. Even when Ollama only runs one request at a time, drafts appear one by one (INT-16), so the admin can start accepting before everything is done.
4. **Plain code where it's reliable.** Parsing, grouping, de-duplicating and checking don't use a model at all.

## Modules
```
order_taker/agents/
  chat_parser.py   # INT-1, INT-2: parse_chat(text) -> list[Message]
  master.py        # IntakeRun: orchestrates, owns semaphore, emits progress
  sorter.py        # INT-7..9
  extractor.py     # INT-10..13 (evolves today's extract.py prompt)
  checker.py       # INT-14 (pure functions, no model)
  ollama.py        # async chat(model, messages, schema) with timeout + 1 retry
```

### Message, Group
```python
class Message(BaseModel):
    sent_at: datetime | None; sender: str; text: str
    def key(self) -> str: sha256(f"{sent_at}|{sender}|{text}")   # INT-3

class SenderGroup(BaseModel):
    sender: str; phone: str | None; messages: list[Message]
```
The sender's phone comes from the WhatsApp contact name when that is a number (unsaved contacts show up as `+91 98450 12345`). Otherwise it is filled in later by the extractor if the messages mention it.

### Sorter schema
```python
class SortResult(BaseModel):
    kind: Literal["new_order", "change", "cancel", "question", "chit_chat"]
    reason: str  # ≤ 12 words; written to the server log only, never shown in the UI (see 004 PRG-3)
```
Prompt: a few lines plus 5 short examples, `temperature 0`, `num_predict 64`.

### Extractor schema (INT-11)
```python
class DraftAction(BaseModel):
    action: Literal["new", "update", "cancel"]
    target_order_id: int | None
    order: Order | None          # existing Order model; None for cancel
class ExtractResult(BaseModel):
    actions: list[DraftAction]
```
The prompt includes the sender's open orders as a compact list (`#12: 2 box brownies, 2026-10-04, ...`), so the model can point at an ID. The Checker then rejects any `target_order_id` that isn't in that list (INT-14).

### Dates and phones in code (INT-21, INT-22)
`agents/dates.py` has `resolve_date(written, ref) -> str`: ISO dates pass through. Relative words, weekday names and day + month become ISO dates. Anything else is returned unchanged, so the Checker flags it. `ref` is the date of the sender's last message, so "kal" said at 11 pm yesterday still means today. `extractor.py` post-processes every action with it and fills an empty phone with `PHONE_RE` from the messages. Small models are bad at calendar arithmetic, while a lookup table is reliable.

### Skipping the sorter (INT-9, amended)
`ExtractResult` also has `kind` (same values as `SortResult`). When no smaller sorter model is available, the master calls only the Extractor and uses its `kind`: no actions + `chit_chat` → chatting; no actions + `question` → needs a reply. That's one 7B call per sender instead of two.

### Prompt caching
The Extractor's system prompt is identical for every call. The sender's name, open orders and messages all go in the user message, so Ollama can reuse the work it already did on the shared prefix. On a laptop where the model only partly fits on the GPU, prompt processing is a large part of each call.

### Small talk in code (INT-8)
`chat_parser.is_small_talk(group)` is true only when no message contains a digit and every word is in a fixed greeting/thanks vocabulary (English plus common Hindi/Kannada/Tamil words in English letters). It's deliberately strict: one unknown word and the model decides.

### Checker (INT-14)
Pure function `check(draft, open_orders, other_drafts, today) -> list[str]`. Each flag is a fixed plain-English sentence, never model text.

### Run lifecycle
- `IntakeRun` is created by `POST /admin/intake` and runs as a background `asyncio.Task` in the server process. A module-level lock enforces INT-6.
- Each sender task saves its drafts and marks its messages as seen **after** its drafts are stored, so a crash doesn't lose messages.
- If one sender's task fails, that failure is turned into a flagged draft (INT-12) and the other senders carry on.

## Ollama tuning (documented in README)
- `OLLAMA_NUM_PARALLEL=3` on the Ollama side gives real concurrency. If it isn't set, calls queue up, which is still correct, just slower.
- Using two models (3B + 7B) means both stay loaded, about 7 GB of RAM. On low-RAM laptops, set `ORDER_SORTER_MODEL` to the same value as `ORDER_MODEL` so Ollama doesn't swap models back and forth, which costs more than it saves.
- `keep_alive: "30m"` on every call, so the models stay warm through a busy evening.

## Trade-offs considered
- **One call per message** instead of per sender: rejected. Edits like "sorry make it 3 boxes" need the earlier message for context.
- **Model-based checker**: not in v1. Fixed rules are instant, predictable and testable. We can revisit if admins see misses.
- **Agent framework (LangGraph/CrewAI)**: rejected. The flow is a fixed pipeline that `asyncio` handles in about 150 lines. A framework would add dependencies and hide the progress events we need for 004.

## Tests
- `chat_parser`: iOS, Android, multi-line, system lines, no timestamps.
- Fake Ollama with per-call delay + canned JSON: concurrency (INT-5, INT-19), skip chit-chat (INT-8), retry then flag (INT-12), seen-message skip on second run (INT-3), drafts appear before run ends (INT-16).
- `checker`: one test per flag.
- `scripts/bench_intake.py` (INT-20) is run by hand, not in CI.
