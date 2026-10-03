# 006 Hosted Demo: Requirements

Status: Implemented

## Context
For the Hacktoberfest submission, judges need a link they can click. The app will run as a public demo on Hugging Face Spaces (one Docker container with the app and Ollama, on free CPU hardware). On the internet, the first visitor must not be able to claim the shop, judges need something to try straight away, and nobody should be tempted to enter real personal data.

This is the deliberate exception to constitution §1 ("reachable only on the local network"). A real shop still runs it on their own laptop.

## User stories
- **US-1** As the developer, I set the shop owner's login through Space secrets, so no stranger can take over the demo through `/setup`.
- **US-2** As a judge, I open the link and immediately see a working shop: example orders, a sample chat to paste, and logins to try both sides.
- **US-3** As a visitor, I'm clearly told this is a demo and not to enter real names, numbers or addresses.

## Acceptance criteria
| ID | Criterion |
|---|---|
| HOST-1 | WHEN `ORDER_ADMIN_USERNAME` and `ORDER_ADMIN_PASSWORD` are set, THE SYSTEM SHALL create that admin on startup if none exists, or update its password to match if it does. `ORDER_SHOP_NAME` and `ORDER_SHOP_WHATSAPP` set the shop details. `/setup` SHALL then return 404. |
| HOST-2 | WHEN `ORDER_SECURE_COOKIES=1`, session cookies SHALL be sent over HTTPS only. `ORDER_COOKIE_SAMESITE` SHALL accept `lax` (default), `strict` or `none`. `none` is only allowed together with secure cookies. |
| HOST-3 | `GET /healthz` SHALL return 200 with `{"ok": true, "ai_ready": <bool>}` without needing a login, and SHALL NOT fail when the AI helper is still starting. |
| HOST-4 | WHEN `ORDER_DEMO=1`, every page SHALL show a banner: "This is a demo. Please don't enter real names, phone numbers or addresses. Everything resets when the demo restarts." |
| HOST-5 | WHEN `ORDER_DEMO=1` and there are no orders, THE SYSTEM SHALL load example customers and orders in different stages on startup, including a demo customer who can log in. None of the sample chat's senders SHALL be among them, so the sample chat still produces new orders. |
| HOST-6 | WHEN `ORDER_DEMO=1`, the login page SHALL show the demo logins for both tabs (shop owner and customer), and the intake page SHALL have a **Use the sample chat** button that fills in `samples/sample_chat.txt`. |
| HOST-7 | Pasted or uploaded chats longer than `ORDER_MAX_CHAT_CHARS` (default 50 000) SHALL be refused with: "That's a very long chat. Please paste just the recent messages." |
| HOST-8 | The listening port SHALL come from `ORDER_PORT` (Hugging Face uses 7860), and links sent to customers SHALL use `ORDER_PUBLIC_URL`. |

## Out of scope
- Keeping data between restarts (the free Space disk resets), multiple shops, rate limiting beyond INT-6's one run at a time.
