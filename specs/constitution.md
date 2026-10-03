# Constitution

Status: Approved

These rules apply to every spec, design and line of code. If a feature needs to break one, change this file first, in its own reviewed change.

## 1. Local-first privacy
- Customer names, phone numbers, addresses and chats are processed and stored **only on the business owner's machine**.
- No external APIs, analytics, CDNs or telemetry. All CSS and JS is served from the app itself.
- The app is reachable only on the local network (same Wi‑Fi). Exposing it to the internet needs a spec change.
- Real chats and the database stay out of git (`chats/`, `data/` are git-ignored).

## 2. Spec first
- No feature code without an approved `requirements.md` and `design.md`.
- Every acceptance criterion has a stable ID and at least one automated test that names it.

## 3. Written for non-technical people
- Every message a user sees (errors, progress, statuses) is plain English that a home baker or their customer understands. No stack traces, model names, JSON or jargon in the UI.
- Mobile-first: every page works on a 360px-wide phone screen.

## 4. Open models, swappable
- AI runs through Ollama. Model names come from env vars and are never hard-coded in logic.
- Model output is always constrained by a JSON schema and validated with Pydantic before it is used.
- The AI proposes, a human decides: nothing extracted by a model becomes a real order until the admin accepts it.

## 5. Fast enough to trust
- Use plain code wherever it's reliable (parsing, matching, validation). Use a model only for understanding language.
- Independent model calls run concurrently, bounded by a configurable limit.

## 6. Small and boring
- Python 3.11+, FastAPI, SQLite (stdlib `sqlite3`), Jinja2 templates, vanilla JS. Adding a dependency needs a reason in the design doc.
- Tests run without Ollama (model calls are faked) and without network access.

## 7. Secure by default
- PINs and passwords are stored only as salted hashes (`hashlib.scrypt`). The one exception is a **starter PIN** the shop issues: it's also kept readable so the shop can resend it, and it's erased the moment the customer chooses their own PIN. A PIN the customer chose is never readable by anyone. *(Amended: shop needs to resend lost starter PINs.)*
- Sessions use signed, HTTP-only cookies. Every page and API checks the user's role on the server.
- A customer can only ever see their own orders.
