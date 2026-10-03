# 007 Guided Tour: Requirements

Status: Implemented

## Context
Judges (and new shop owners) land on the site with no idea where to start. A short guided tour should highlight the important parts of each page one at a time and explain them in plain English. There's one tour for the shop owner and one for customers. For customers the key message is the PIN: they need one from the shop.

## User stories
- **US-1** As a first-time visitor, I'm shown around each page the first time I open it, so I know what to do.
- **US-2** As a customer at the login page, I'm told I need a PIN and that the shop I ordered from gives it to me.
- **US-3** As anyone, I can skip the tour at any time and replay it later.

## Acceptance criteria
| ID | Criterion |
|---|---|
| TOUR-1 | THE SYSTEM SHALL have tours for: the customer login tab, the shop-owner login tab, the admin order board, the admin add-orders page, and the customer's orders page. Other pages have none. |
| TOUR-2 | Each step SHALL highlight one part of the page (the rest is dimmed) and show a short title, a plain-English explanation, "Step X of Y", and **Back**, **Next** (**Done** on the last step) and **Skip tour**. |
| TOUR-3 | The customer login tour SHALL highlight the PIN field with: "A PIN is needed. Ask the shop you ordered from for your PIN; they'll send it to you on WhatsApp." |
| TOUR-4 | A tour SHALL start by itself the first time a browser opens that page, and not again after it's finished or skipped. A **Show me around** button in the header SHALL replay it whenever there's a tour for the page. |
| TOUR-5 | Steps whose part of the page isn't there (e.g. no orders yet, no customer changes) SHALL be skipped silently. Demo-only steps (demo logins, sample chat) SHALL only appear when `ORDER_DEMO=1`. |
| TOUR-6 | Tour text SHALL follow constitution §3: no technical words. The same banned-word test as PRG-4 applies. |
| TOUR-7 | The tour SHALL work on a 360px-wide phone (the explanation sits above or below the highlighted part, or at the bottom of the screen if neither fits), close with **Esc**, move with the arrow keys, be announced to screen readers as a dialog, and not animate when the device asks for reduced motion. |
| TOUR-8 | Tours SHALL use no external libraries or network requests (constitution §1). Whether a tour has been seen is stored only in that browser (localStorage) and the page works normally if storage is unavailable. |
