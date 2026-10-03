# 004 Live Progress Feed: Design

Status: Implemented

## Event model
```python
class ProgressEvent(BaseModel):
    seq: int                       # 1, 2, 3… per run
    at: datetime
    kind: Literal["info", "working", "done", "warn", "error", "summary", "draft_ready"]
    text: str                      # rendered from a template
    sender: str | None = None
    draft_id: int | None = None    # for draft_ready: UI fetches the card
    done_count: int; total_count: int
```

## Templates (PRG-3, PRG-4)
`order_taker/progress.py` holds a single `TEMPLATES: dict[str, list[str]]`. Each key has one or more wordings, and `say(key, **kw)` picks one (varied wording for the heartbeat, PRG-5). The agents call `run.say("sorted.chit_chat", name="Meena")`. They never build strings themselves.

A test renders every template with sample values and checks it against a banned-word list (PRG-4). Another test greps `agents/` to make sure there are no string literals passed to `say`.

## Transport: Server-Sent Events
- `GET /admin/intake/{run_id}/events` (admin only, PRG-10) returns `text/event-stream`.
- Each run keeps its events in an in-memory list plus an `asyncio.Condition`. A client sends `Last-Event-ID` (the browser does this automatically on reconnect), and the server replays every event after that `seq`, then waits for more (PRG-8).
- On finish, the summary is also saved to `intake_runs.summary`, so the page can show it after a server restart.
- Chosen over WebSockets: SSE is one-way, works through `StreamingResponse` with no extra dependency, and reconnects on its own.

## Heartbeat (PRG-5)
Each sender task wraps its model step in `async with run.heartbeat(name)`. A side task posts `still_working` every 15s until the block exits.

## UI
```
┌ What's happening ─────────── 2 of 4 people done · 0:23 ┐
│ ✓ Found messages from 4 people: Priya, Rahul…          │
│ ✓ Meena is just saying good night. Nothing to order.   │
│ … Priya wants to order something. Writing down…        │
│ ✓ Sneha's order is ready for you to check.             │
└────────────────────────────────────────────────────────┘
[ draft cards appear below as each one is ready ]
```
- `static/progress.js` (~60 lines): `new EventSource(url)`, append `<li>`, auto-scroll unless the user has scrolled up, update the counter and timer. On `draft_ready`, fetch `/admin/drafts/{id}/card` (an HTML fragment) and insert it.
- Icons are text glyphs (✓ … ⚠ ✗ ★) with `aria-hidden`. The words carry the meaning (PRG-9).
- After the summary, the box shrinks to its last line with a "Show details" toggle.

## Tests
- Template rendering + banned words (PRG-3, PRG-4).
- Heartbeat with a fake slow model and the interval patched to 0.1s (PRG-5).
- SSE replay from `Last-Event-ID` (PRG-8).
- A customer gets 403 on the events URL (PRG-10).
