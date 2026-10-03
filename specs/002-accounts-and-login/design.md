# 002 Accounts & Login: Design

Status: Implemented

## Modules
- `order_taker/auth.py`
  - `normalise_phone(raw) -> str | None`: strips non-digits, removes a `91` prefix from 12 digits or a `0` from 11, and returns the 10 digits that remain, or `None` (AUTH-3). `PHONE_RULE` holds the AUTH-15 message so every form uses the same words.
  - `hash_secret(s) / verify_secret(s, h)`: `hashlib.scrypt` (n=2**14, r=8, p=1), 16-byte salt, stored as `scrypt$<salt_b64>$<hash_b64>`. Compared with `hmac.compare_digest`.
  - `new_pin() -> str`: `secrets.randbelow(10**6)`, zero-padded to 6 digits.
  - `ensure_customer(conn, name, phone) -> (user, pin | None)`: used when an order is accepted.
- `web/deps.py`: `current_user`, `require_admin`, `require_customer` (FastAPI dependencies). A customer with `must_change_pin` gets redirected to `/change-pin`.
- `web/routes_auth.py`: `/setup`, `/login`, `/logout`, `/change-pin`.

## Routes
| Method + path | Who | Notes |
|---|---|---|
| GET/POST `/setup` | anyone, only while no admin exists | AUTH-1 |
| GET/POST `/login` | anyone | form field `kind=customer|admin` (AUTH-2) |
| POST `/logout` | logged in | clears the session |
| GET/POST `/change-pin` | customer | AUTH-6 |
| POST `/admin/customers/{id}/reset-pin` | admin | AUTH-8 |
| GET `/` | anyone | redirects by role: admin → `/admin`, customer → `/my-orders`, else → `/login` |

## Lockout (AUTH-7)
`failed_attempts` and `locked_until` live on `users`. A successful login resets them. An unknown phone runs a dummy hash check so the response time doesn't reveal whether an account exists (AUTH-12).

## CSRF
Forms are same-origin and cookies are SameSite=Lax. Every state-changing POST also checks a per-session CSRF token in a hidden field.

## WhatsApp share text (AUTH-4)
Shown in a read-only textarea with a **Copy** button (`navigator.clipboard.writeText`). A `https://wa.me/91XXXXXXXXXX?text=...` link is shown too, so on a phone the admin can open WhatsApp with the message ready to send. The app never sends anything itself.

## Starter PIN (AUTH-13, AUTH-14)
Migration `0003_starter_pin.sql` adds `users.starter_pin TEXT`. `ensure_customer` and `reset_pin` write the plain PIN there as well as the hash. `change_pin` sets it to NULL in the same UPDATE. Login still checks only the hash. This was a deliberate trade-off: the starter PIN is a one-time code that the shop already knows and sends over WhatsApp, so keeping it readable until first use adds no new exposure. Customer-chosen PINs, which people often reuse elsewhere, stay hash-only.

## Tests
One test per AUTH ID. Phone normalisation gets a table-driven test. The role checks (AUTH-10) are tested by having a customer hit every `/admin/*` route.
