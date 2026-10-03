# 002 Accounts & Login: Requirements

Status: Implemented

## Context
There are two kinds of people: the **admin** (the business owner who takes orders) and **customers** (who want to check their own orders). Customers order over WhatsApp, so their phone number is the natural identity. There's no SMS service (constitution §1), so customers use a PIN that the admin shares.

## User stories
- **US-1** As the admin, I set up my login once and then log in with a username and password.
- **US-2** As the admin, when I accept an order from a new phone number, a customer account is created for them automatically and I get a PIN to send them on WhatsApp.
- **US-3** As a customer, I log in with my phone number and PIN and see only my orders.
- **US-4** As a customer, I can change the PIN the admin gave me.
- **US-5** As the admin, I can reset a customer's PIN if they forget it.

## Acceptance criteria
| ID | Criterion |
|---|---|
| AUTH-1 | WHEN no admin exists, THE SYSTEM SHALL show a one-time "Set up your shop" page to create the admin (name, username, password ≥ 8 characters) and enter the shop name and WhatsApp number (TRK-11). After that the page SHALL no longer be available. |
| AUTH-2 | THE SYSTEM SHALL provide one login page with two tabs: **"I'm a customer"** (phone + PIN) and **"Shop owner"** (username + password). |
| AUTH-3 | THE SYSTEM SHALL normalise phone numbers before storing or matching them (strip spaces, dashes and brackets; `+91`, `91` and `0` prefixes on 10-digit Indian mobiles map to the same number), so `98450 12345`, `+91-98450-12345` and `098450 12345` are one customer. |
| AUTH-4 | WHEN the admin accepts an order whose phone matches no customer, THE SYSTEM SHALL create a customer account, generate a random 6-digit PIN, show it once to the admin, and offer a ready-to-copy WhatsApp message: "Hi {name}, you can track your order at {wifi-url}. Login: your phone number, PIN {pin}". |
| AUTH-5 | WHEN an order has no phone number, THE SYSTEM SHALL still save it, mark it "No phone – customer can't track this", and let the admin add a phone later, which links the order to a customer and triggers AUTH-4 if needed. |
| AUTH-6 | WHEN a customer logs in with an admin-issued PIN, THE SYSTEM SHALL ask them to choose a new 4–6 digit PIN before showing anything else. |
| AUTH-7 | WHEN there are 5 wrong attempts in a row for one account, THE SYSTEM SHALL lock that account for 15 minutes and say: "Too many tries. Please wait 15 minutes or ask the shop to reset your PIN." |
| AUTH-8 | The admin SHALL be able to reset any customer's PIN (a new PIN is shown once, then AUTH-6 applies). |
| AUTH-9 | THE SYSTEM SHALL store PINs and passwords as salted scrypt hashes. A PIN the customer chose SHALL only ever be stored as a hash. |
| AUTH-13 | THE SYSTEM SHALL also keep a starter PIN (from AUTH-4 or AUTH-8) readable until the customer replaces it (AUTH-6), then erase it, so the admin can resend it if it's lost. |
| AUTH-14 | The admin SHALL be able to give a customer a new login with one tap from their order card (a new starter PIN, as in AUTH-8). The PIN page then offers the ready WhatsApp message. |
| AUTH-10 | Every admin page and API SHALL return 403 to customers, and every customer page SHALL show only orders whose `customer_id` is the logged-in user. Checked on the server, never only in the UI. |
| AUTH-11 | Sessions SHALL use signed HTTP-only cookies (SameSite=Lax) that expire after 30 days for customers and 12 hours for the admin. The signing secret is generated on first start and kept in `data/secret.key`. |
| AUTH-12 | Login error messages SHALL NOT reveal whether a phone number has an account ("That phone number and PIN don't match"). |

## Out of scope
- Multiple admins or staff roles, customer self-signup, OTP.
