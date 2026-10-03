# 005 Order Tracking: Requirements

Status: Implemented

## Context
Once the admin accepts an order, it moves through simple stages. The admin moves it along with one tap, and the customer sees where it is from their phone.

## Look and feel
Warm bakery palette: cream background, cocoa text and header, raspberry for primary actions, mint for done or OK, caramel for warnings. There's a matching dark mode that follows the phone or laptop setting. Text keeps WCAG AA contrast in both modes. *(Added after first release.)*

## Statuses
| Status | Admin sees | Customer sees |
|---|---|---|
| `received` | Received | We've got your order |
| `confirmed` | Confirmed | Confirmed by the shop |
| `preparing` | Preparing | Being made |
| `ready` | Ready | Ready for pickup / Ready for delivery *(depending on whether there's an address)* |
| `delivered` | Delivered | Delivered. Enjoy! |
| `cancelled` | Cancelled | Cancelled |

## User stories
- **US-1** As the admin, I see today's and upcoming orders on one board and move each one along with a single tap.
- **US-2** As the admin, I still get my per-day prep list and a CSV download.
- **US-3** As a customer, I open the link, log in, and immediately see my upcoming orders and their stage.
- **US-4** As a customer, I can change or cancel my order in the app, without having to message the shop.
- **US-5** As the admin, I can see clearly what a customer changed, and I approve changes to orders I've already confirmed, so nothing changes behind my back once I've started planning.

## Acceptance criteria

### Lifecycle
| ID | Criterion |
|---|---|
| TRK-1 | WHEN the admin accepts a `new` draft, THE SYSTEM SHALL create an order with status `received` and run the customer-account step (AUTH-4/AUTH-5). |
| TRK-2 | WHEN the admin accepts an `update` draft, THE SYSTEM SHALL apply the new details to the existing order, keep its status, and record "Changed by customer on {date}" in its history. WHEN the order is already `preparing` or later, accepting SHALL first ask: "This order is already being made. Apply the change anyway?" |
| TRK-3 | WHEN the admin accepts a `cancel` draft, THE SYSTEM SHALL set the order to `cancelled`. |
| TRK-4 | Statuses SHALL only move forward one step at a time (received → confirmed → preparing → ready → delivered). `cancelled` SHALL be reachable from any status except `delivered`. |
| TRK-5 | The admin SHALL be able to undo the last status change within 5 minutes (a misclick). |
| TRK-6 | Every status change SHALL be recorded with who made it and when. |

### Admin board
| ID | Criterion |
|---|---|
| TRK-7 | THE SYSTEM SHALL show an orders board with tabs **Today**, **Tomorrow**, **Upcoming**, **No date** and **Past**, each sorted by delivery time. |
| TRK-8 | Each order card SHALL show the customer, items, time, address or "Pickup", notes, status, and one primary button for the next step (e.g. **Start preparing**), plus a menu with **Cancel order** and **Edit**. Orders linked to a customer SHALL also show their login: the starter PIN with **Copy** and **Send on WhatsApp** while it's unused (AUTH-13), otherwise "Has their own PIN" and a **Send new login** button (AUTH-14). |
| TRK-9 | THE SYSTEM SHALL show the prep list for any chosen day (total of each item, excluding cancelled orders) and offer a CSV download of the orders shown. |
| TRK-29 | On the admin **Edit order** page, the phone SHALL be editable. Changing it SHALL relink the order to the customer with that number, creating the account and a starter PIN if needed (as in AUTH-5). *(Bug found during build: the phone field was shown but ignored.)* |
| TRK-10 | The admin SHALL see a list of customers with their phone, number of orders, their starter PIN if still unused (AUTH-13), and **Reset PIN** (AUTH-8). |
| TRK-11 | On first setup, the admin SHALL enter the shop's name and WhatsApp number. These are used on customer pages (TRK-14) and can be changed later in Settings. |

### Customer view
| ID | Criterion |
|---|---|
| TRK-12 | WHEN a customer logs in, THE SYSTEM SHALL show their non-delivered, non-cancelled orders first (soonest first), each with items, date/time, notes and a 5-step progress bar for the current stage. |
| TRK-13 | Delivered and cancelled orders SHALL appear under a collapsed "Past orders" section. |
| TRK-14 | Each order SHALL show a **Change order** button (see Customer edits below) and, as a secondary option, "Or message {shop name} on WhatsApp" with a `wa.me` link to the shop number, pre-filled with the order's date and items. |
| TRK-15 | Each order SHALL show when its status last changed ("Updated 10 minutes ago"), and the page SHALL refresh its data whenever it's brought back to the screen. |
| TRK-16 | The customer page SHALL NOT show other customers' data, admin-only notes, or the internal status history (only the current stage and when it changed). |

### Customer edits
What a customer's change does depends on the order's stage:

| Order status | Customer can… | Effect |
|---|---|---|
| `received` | edit or cancel | Applied **immediately**; admin is notified |
| `confirmed`, `preparing`, `ready` | edit or cancel | Sent as a **request**; applied only when the admin approves |
| `delivered`, `cancelled` | nothing | No Change button |

| ID | Criterion |
|---|---|
| TRK-17 | The customer SHALL be able to change items (name, quantity, unit; add or remove lines), delivery date, delivery time, delivery address / pickup, and notes. Name and phone SHALL NOT be editable. At least one item SHALL remain; quantities SHALL be > 0; the date SHALL NOT be in the past. Validation messages SHALL be plain English. |
| TRK-18 | The customer SHALL be able to cancel the order from the same screen, after a confirmation step ("Cancel this order? The shop will be told."). |
| TRK-19 | WHEN the order is `received`, THE SYSTEM SHALL apply the change or cancellation immediately, record it in the history as "Changed by customer", and show the customer "Done, your order is updated." |
| TRK-20 | WHEN the order is `confirmed`, `preparing` or `ready`, THE SYSTEM SHALL save the change as a pending request, leave the order unchanged, and show the customer "Change requested. Waiting for {shop name} to approve." on the order. |
| TRK-21 | An order SHALL have at most one pending customer request. While one is pending, the customer SHALL be able to edit it again (which replaces it) or **withdraw** it. |
| TRK-22 | WHEN the admin approves a request, THE SYSTEM SHALL apply it (same rules as TRK-2/TRK-3) and show the customer "Your change was approved." WHEN the admin declines, the order SHALL stay unchanged and the customer SHALL see "Your change wasn't approved", plus the admin's optional reason. |
| TRK-23 | WHEN the admin moves an order from `received` to `confirmed`, any further customer change SHALL become a request (TRK-20), even if the customer opened the edit screen before the status changed. The rule is checked when the change is saved, not when the screen opens. |

### Admin side of customer edits
| ID | Criterion |
|---|---|
| TRK-24 | THE SYSTEM SHALL show a **Customer changes** section at the top of the admin board, with a count badge in the navigation, listing pending requests first, then changes applied directly in the last 48 hours. |
| TRK-25 | Each entry SHALL show the customer, the order, and an **old → new** comparison of only the fields that changed (items added, removed or changed shown line by line). Pending requests SHALL have **Approve** and **Decline** (with an optional reason) buttons; directly applied changes SHALL have **Got it**, which marks them seen. |
| TRK-26 | Order cards on the board SHALL show a "Changed by customer" badge until the admin has seen the change, and a "Change requested" badge while a request is pending. |
| TRK-27 | WHEN a chat-based update draft (003) and an in-app request are both pending for the same order, both SHALL show the flag "There's another change waiting for this order", so the admin decides which one wins. |
| TRK-28 | Customer edits and requests SHALL appear in the order's history with who made them and when (TRK-6). |
