# 002 Accounts & Login: Tasks

- [x] T1. `auth.py`: `normalise_phone`, scrypt hash/verify, `new_pin` + tests (AUTH-3, AUTH-9)
- [x] T2. Secret key bootstrap in `data/secret.key` + SessionMiddleware config (AUTH-11)
- [x] T3. `/setup` one-time admin creation (AUTH-1)
- [x] T4. `/login` with customer/admin tabs, generic errors, lockout (AUTH-2, AUTH-7, AUTH-12)
- [x] T5. `deps.py` role guards + CSRF token helper; test every admin route as a customer (AUTH-10)
- [x] T6. `/change-pin` + forced change on first login (AUTH-6)
- [x] T7. `ensure_customer` + PIN reveal + WhatsApp share text on order accept (AUTH-4) *(wired in 005)*
- [x] T8. "No phone" handling + add-phone-later flow (AUTH-5)
- [x] T9. Admin PIN reset (AUTH-8)
- [x] T10. Migration 0003 `users.starter_pin`; set on create/reset, cleared on change (AUTH-13)
- [x] T11. One-tap "Send new login" from the order card (AUTH-14)
- [x] T12. Strict 10-digit phone rule + same message on every form (AUTH-3, AUTH-15)
