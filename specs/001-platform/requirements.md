# 001 Platform: Requirements

Status: Implemented

## Context
Today the app is a single Gradio page that forgets everything when it closes. To support logins, saved orders and live progress, it needs a proper web app with a database that phones on the same Wi‑Fi can reach.

## User stories
- **US-1** As the admin, I start the app with one command and it tells me the address to open on my laptop and the address customers can use on their phones.
- **US-2** As the admin, I want orders to survive restarts so I never lose a day's work.
- **US-3** As the admin, I want to choose which AI models are used without touching code.

## Acceptance criteria
| ID | Criterion |
|---|---|
| PLT-1 | WHEN the admin runs `python app.py`, THE SYSTEM SHALL start a web server on port 8000 (override: `ORDER_PORT`) listening on all local network interfaces. |
| PLT-2 | WHEN the server starts, THE SYSTEM SHALL print the laptop URL (`http://127.0.0.1:<port>`) and the Wi‑Fi URL (`http://<lan-ip>:<port>`) in plain English. |
| PLT-3 | THE SYSTEM SHALL store all data in a single SQLite file at `data/order_taker.db` (override: `ORDER_DB`), creating it and its tables on first start. |
| PLT-4 | WHEN the database schema changes in a later version, THE SYSTEM SHALL upgrade an existing database in place without losing data (numbered migrations). |
| PLT-5 | THE SYSTEM SHALL read model settings from env vars: `ORDER_MODEL` (default `qwen2.5:7b`), `ORDER_SORTER_MODEL` (default `qwen2.5:3b`), `OLLAMA_URL` (default `http://localhost:11434`), `ORDER_PARALLEL` (default `3`). |
| PLT-6 | WHEN Ollama is unreachable, THE SYSTEM SHALL still start and serve every page except intake, and intake SHALL show: "The AI helper isn't running. Open the Ollama app and try again." |
| PLT-7 | THE SYSTEM SHALL serve all CSS and JS itself and load nothing from the internet. |
| PLT-8 | THE SYSTEM SHALL keep `data/` and `chats/` out of git. |
| PLT-9 | THE SYSTEM SHALL keep the existing CSV export and per-day prep list, now built from saved orders. |

## Out of scope
- HTTPS, internet hosting, multiple businesses on one install.
