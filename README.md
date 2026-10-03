# Order Taker 🧁

Turns messy WhatsApp order messages into clean orders for a small home business. The shop owner pastes the chat, a team of small AI helpers reads it, and customers can log in from their phones to see where their order is.

Everything runs on the shop owner's laptop with an open-weight model via [Ollama](https://ollama.com), so customer names, numbers and addresses never leave the machine.

## What it does

- **Shop owner** (admin): paste or upload the WhatsApp chat. Watch a plain-English "What's happening" feed while it's read. Check, edit and accept each order, then move it along: Received → Confirmed → Preparing → Ready → Delivered.
- **Customers**: log in with their phone number and a PIN the shop sends them. They can see their order's progress, and change or cancel it. Once the shop has confirmed an order, changes need the shop's approval.
- **Prep list and CSV**: what to make each day, and a spreadsheet of orders.

## Setup

```bash
# 1. Ollama + a model (one time)
ollama pull qwen2.5:7b        # ~4.7 GB; use qwen2.5:3b on low-RAM laptops

# 2. Python env
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# 3. Run
python app.py
```

It prints two addresses:

```
Order Taker is running.
  On this laptop:          http://127.0.0.1:8000
  On phones (same Wi-Fi):  http://192.168.1.23:8000
```

The first time you open it, you'll set up the shop (your login, the shop name and its WhatsApp number). On Windows, allow the firewall prompt for **Private networks** so phones on your Wi‑Fi can reach it.

In VS Code: **Run and Debug → Run Order Taker**.

Try it with `samples/sample_chat.txt`. Put real chats in `chats/`; the database lives in `data/`. Both are git-ignored.

## How the AI helpers work

```
pasted chat ─▶ Master (plain code): split by person, skip messages already read,
                spot pure "good night / thank you" without any AI
                  │  one track per person, all at the same time
                  ├─▶ [Sorter, small model*] ─▶ [Extractor, main model] ─▶ [Checker, plain code] ─▶ draft
                  └─▶ …
```

- **Extractor**: reads one person's messages and their earlier open orders. It works out new orders, changes and cancellations.
- **Dates and phone numbers are finished off in code.** "Sunday", "kal" and "5th Oct" are converted relative to when the message was sent. Small models are unreliable at calendar maths.
- **Checker**: fixed rules that flag a missing date, a missing address or pickup, a missing phone, duplicates, and so on.
- Nothing becomes a real order until the shop owner accepts it.

\* The Sorter only runs when a smaller model (`ORDER_SORTER_MODEL`) is installed. Otherwise the Extractor also sorts, in the same call.

## Config

| Env var | Default | |
|---|---|---|
| `ORDER_MODEL` | `qwen2.5:7b` | Main model, e.g. `llama3.2`, `gemma2:9b` |
| `ORDER_SORTER_MODEL` | `qwen2.5:3b` | Small model for sorting; skipped if not installed |
| `ORDER_PARALLEL` | `3` | Max model calls at once |
| `OLLAMA_URL` | `http://localhost:11434` | |
| `ORDER_PORT` | `8000` | |
| `ORDER_DB` | `data/order_taker.db` | |

### Making it faster (Ollama settings)

The helpers send one request per person at the same time. Whether Ollama runs them at the same time depends on your machine:

- **GPU with room to spare** (the model fits fully in VRAM, with space left over): set `OLLAMA_NUM_PARALLEL=3` for Ollama and restart it. People are then processed together.
- **Small GPU or CPU only** (e.g. a 4 GB GTX 1650 running a 7B model): Ollama handles one request at a time. The whole batch takes about as long as before, but each order shows up as soon as it's ready, so you can start checking straight away. For more speed, use `ORDER_MODEL=qwen2.5:3b`. It's faster but a little less accurate.
- **Low RAM**: don't install a separate sorter model. Swapping two models in and out costs more than it saves.

Benchmark on your machine (uses a throwaway database):

```bash
python scripts/bench_intake.py
```

## Tests

```bash
pytest -q    # no Ollama needed; model calls are faked
```

Every test names the spec criterion it covers (e.g. `INT-4`, `TRK-20`).

## Spec Driven Development

Features are specified before they're built. See [specs/](specs/README.md): a constitution, then requirements → design → tasks for each feature.

## Contributing

Contributions are welcome, especially during Hacktoberfest.

1. Fork the repo and create a branch from `main`.
2. For a new feature or behaviour change, update or add a spec in [specs/](specs/README.md) first.
3. Add tests that name the criteria they cover, and make sure `pytest -q` passes.
4. Open a pull request. `main` is protected: changes go in through a PR with a passing test run and one approving review.

Ideas: more chat languages for date words, more WhatsApp export formats, a printable prep sheet, translations of the UI.

## License

[MIT](LICENSE)

## Why open

- **Privacy:** customer phone numbers and home addresses stay on the laptop.
- **Cost:** zero per-message cost, which matters for a tiny business.
- **Control:** swap models with one env var; structured output is enforced with a JSON schema.
