# 001 Platform: Design

Status: Implemented

## Stack
| Concern | Choice | Why |
|---|---|---|
| Web | FastAPI + Uvicorn | Async, so model calls run concurrently. Has built-in SSE support through `StreamingResponse`. |
| Pages | Jinja2 templates + one hand-written CSS file + small vanilla JS | Works on phones, no build step, no CDN (constitution §1). |
| Storage | stdlib `sqlite3`, WAL mode | Zero setup, one file, easy to back up. |
| Sessions | Starlette `SessionMiddleware` (signed cookie, `itsdangerous`) | Standard, no extra server. |
| Ollama client | `httpx.AsyncClient` | Async; replaces `requests`. |

**Dependency changes:** add `fastapi`, `uvicorn`, `jinja2`, `httpx`, `python-multipart` (form posts) and `itsdangerous`. Remove `gradio`, `pandas` and `requests` (the CSV is written with stdlib `csv`). Dev: add `pytest-asyncio`.

## Layout
```
app.py                       # entry point: prints URLs, runs uvicorn
order_taker/
  config.py                  # env vars -> Settings dataclass
  db.py                      # connection, migrations, small query helpers
  migrations/0001_init.sql
  models.py                  # Pydantic shapes (existing, extended)
  web/
    main.py                  # FastAPI app factory, middleware, routers
    deps.py                  # current_user, require_admin, require_customer
    routes_auth.py  routes_admin.py  routes_customer.py
    templates/  static/
  agents/                    # feature 003
  progress.py                # feature 004
  extract.py                 # kept: prep_list(), orders_table(), helpers
```

## Data model (0001_init.sql)
```sql
users(id PK, role TEXT CHECK(role IN ('admin','customer')), phone TEXT UNIQUE,
      username TEXT UNIQUE, name TEXT, pin_hash TEXT, must_change_pin INT,
      failed_attempts INT DEFAULT 0, locked_until TEXT, created_at TEXT)
orders(id PK, customer_id FK users NULL, customer_name TEXT, phone TEXT,
       delivery_date TEXT, delivery_time TEXT, address TEXT, notes TEXT,
       status TEXT, created_at TEXT, updated_at TEXT)
order_items(id PK, order_id FK, name TEXT, quantity REAL, unit TEXT)
status_history(id PK, order_id FK, status TEXT, changed_by FK users, at TEXT)
intake_runs(id PK, started_by FK, started_at TEXT, finished_at TEXT, summary TEXT)
drafts(id PK, source TEXT CHECK(source IN ('chat','customer')),
       run_id FK NULL,              -- set when source='chat'
       requested_by FK users NULL,  -- set when source='customer'
       action TEXT, target_order_id NULL, payload_json TEXT,
       before_json TEXT,            -- snapshot of the order when the draft was made, for old→new diffs
       flags_json TEXT, decline_reason TEXT,
       state TEXT CHECK(state IN ('pending','accepted','discarded','declined','withdrawn','applied')),
       seen_by_admin INT DEFAULT 0, created_at TEXT, decided_at TEXT)
seen_messages(hash TEXT PK, run_id FK, sender TEXT, sent_at TEXT)
schema_version(version INT)
```
Migrations are numbered `.sql` files. `db.migrate()` applies every file newer than `schema_version`, each one in its own transaction (PLT-4).

## Startup (PLT-1, PLT-2)
`app.py` runs migrations, then finds the LAN IP (UDP-connect trick, no packets sent; falls back to hostname lookup), prints:
```
Order Taker is running.
  On this laptop:      http://127.0.0.1:8000
  On phones (same Wi-Fi): http://192.168.1.23:8000
Press Ctrl+C to stop.
```
then calls `uvicorn.run(app, host="0.0.0.0", port=...)`. The first time it runs on Windows, the firewall will ask for permission. The README explains to choose **Private networks**.

## Ollama health (PLT-6)
`GET {OLLAMA_URL}/api/tags` with a 2s timeout, checked when the intake page loads and again when an intake run starts. Pages that don't use the model never call Ollama.

## Testing
- `tests/conftest.py`: a temp-file DB per test and a FastAPI `TestClient`. A `fake_ollama` fixture patches the Ollama client with canned responses.
