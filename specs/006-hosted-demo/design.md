# 006 Hosted Demo: Design

Status: Implemented

## Settings (config.py)
New fields: `admin_username`, `admin_password`, `shop_name`, `shop_whatsapp`, `secure_cookies`, `cookie_samesite`, `demo`, `max_chat_chars`. All come from env vars and default to off/empty, so a laptop install behaves exactly as before.

## Startup (web/main.py → `bootstrap.py`)
`create_app` runs migrations, then `bootstrap.apply(conn, settings)`:
1. **HOST-1:** if both admin env vars are set: create or update the admin (password hash only), then set the shop name and WhatsApp if given. `settings.env_admin` makes `/setup` return 404.
2. **HOST-5:** if `demo` and `SELECT COUNT(*) FROM orders` is 0, seed the data. Demo customer **Kavya, 98111 22233, PIN 2468** has a ready order and a confirmed one. Arjun has a starter PIN that hasn't been used (so the PIN-on-card feature shows). There's also one delivered order. Seeding uses the real `orders`/`auth` functions, so the history is real.

## Cookies (HOST-2)
`SessionMiddleware(https_only=settings.secure_cookies, same_site=settings.cookie_samesite)`. If `none` is requested without secure cookies, it falls back to `lax`, because browsers reject `SameSite=None` on non-secure cookies. CSRF tokens (AUTH) still protect every POST.

**Why judges should use the direct link:** huggingface.co shows the Space inside an iframe from `*.hf.space`. That makes the session cookie a third-party cookie, which many browsers block whatever the SameSite setting. The DEV post links straight to `https://<user>-order-taker.hf.space`.

## Inside the Hugging Face page (HOST-2, HOST-9, HOST-10)
The Space page on huggingface.co shows the app in an iframe from `*.hf.space`, so for the browser our cookie is a third-party cookie. `SameSite=Lax` cookies aren't sent there, so the CSRF check failed on every form. With `SameSite=None; Secure; Partitioned` (CHIPS), Chrome, Edge and Firefox keep a separate cookie for the app inside that page. Safari blocks third-party cookies in frames altogether, which is why `app.js` shows an "open in its own tab" link when `window.self !== window.top`, and `check_csrf` explains the problem when no session cookie arrives at all.

## Demo UI (HOST-4, HOST-6)
`render()` adds `demo` and `demo_logins` to every template. `base.html` shows the banner. `login.html` shows the demo login for the current tab. `admin_intake.html` gets a button that fills the textarea from a `<template>` holding the sample chat, read once at startup.

## Health (HOST-3)
`/healthz` returns `{"ok": true, "ai_ready": await ollama.healthy()}`. Always 200: a slow model start must not make the platform restart the container.

## Container notes (for the Dockerfile, written by the developer)
- Hugging Face runs the container as **uid 1000**. Everything written at runtime (`ORDER_DB` directory, Ollama models) must be writable by that user.
- Baking the model into the image at build time avoids a 2 GB download on every restart.
- Start `ollama serve` in the background, then `python app.py`. The app already copes with Ollama not being ready yet (PLT-6).
