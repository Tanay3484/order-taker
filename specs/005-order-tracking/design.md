# 005 Order Tracking: Design

Status: Implemented

## State machine
`order_taker/orders.py`
```python
FLOW = ["received", "confirmed", "preparing", "ready", "delivered"]
def next_status(s) -> str | None            # TRK-4
def can_cancel(s) -> bool                   # anything but delivered
def advance(conn, order_id, by_user)        # writes status_history (TRK-6)
def cancel(conn, order_id, by_user)
def undo_last(conn, order_id, by_user)      # only if last change < 5 min ago (TRK-5)
def apply_draft(conn, draft, by_user, force=False)  # TRK-1..3; raises NeedsConfirm for TRK-2
def customer_change(conn, order_id, customer, new_order | None) -> "applied" | "requested"   # TRK-17..23
def decide_request(conn, draft_id, admin, approve: bool, reason="")                          # TRK-22
def withdraw_request(conn, draft_id, customer)                                              # TRK-21
def diff(before: Order, after: Order) -> list[FieldChange]                                  # TRK-25
```
Every function runs in one transaction. The rules live here, never in route handlers.

## Customer edits (TRK-17..28)
Customer changes reuse the **drafts** table (`source='customer'`), so there is one review path for changes from chats and changes from the app, and `apply_draft` is the only code that modifies an order's contents.

`customer_change` runs in `BEGIN IMMEDIATE` (a write lock), so the status is read and acted on together (TRK-23):
1. Check the order belongs to this customer and isn't `delivered`/`cancelled`. Validate the new details (TRK-17).
2. Snapshot the current order into `before_json`.
3. If the status is `received`: call `apply_draft(force=True)`, store the draft with `state='applied', seen_by_admin=0`, and return `"applied"` (TRK-19).
4. Otherwise: mark any existing pending customer draft for this order `withdrawn`, insert the new one as `pending`, and return `"requested"` (TRK-20, TRK-21).

**Admin "Customer changes" list (TRK-24)** = `source='customer' AND (state='pending' OR (state='applied' AND seen_by_admin=0) OR (state='applied' AND created_at > now-48h))`. The nav badge counts pending + unseen.

**Conflict flag (TRK-27)**: when the board or intake page renders, any two `pending` drafts with the same `target_order_id` both get the flag. Checked at render time, so it's always current.

**Customer edit form**: a server-rendered form with item rows. "Add item" and "Remove" use about 30 lines of vanilla JS that clone/remove a row (without JS it falls back to 3 blank rows). The date input has `min=today`, and the server checks it again. The address field has a "Pickup instead" checkbox.

**Stale `before_json`**: if the admin edits the order while a request is pending, approving the request still applies the customer's full new details. The diff shown at approval is calculated against the **current** order, not `before_json`, so the admin sees what will actually change.

## Schema additions (migration 0002)
```sql
CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);   -- shop_name, shop_whatsapp (TRK-11)
ALTER TABLE orders ADD COLUMN admin_note TEXT DEFAULT '';  -- never shown to customers (TRK-16)
```

## Routes
| Method + path | Who | |
|---|---|---|
| GET `/admin` | admin | board, `?tab=today|tomorrow|upcoming|nodate|past` (TRK-7) |
| POST `/admin/orders/{id}/advance` · `/cancel` · `/undo` | admin | TRK-4, TRK-5 |
| GET/POST `/admin/orders/{id}/edit` | admin | |
| POST `/admin/drafts/{id}/accept` · `/discard` | admin | TRK-1..3; may reply "needs confirm" |
| GET `/admin/prep?date=` · `/admin/orders.csv?tab=` | admin | TRK-9 |
| GET `/admin/customers` | admin | TRK-10 |
| GET/POST `/admin/settings` | admin | TRK-11 |
| GET `/my-orders` | customer | TRK-12..15 |
| GET `/my-orders.json` | customer | used by the refresh-on-focus script (TRK-15) |
| GET/POST `/my-orders/{id}/change` | customer | edit form + save (TRK-17, TRK-19, TRK-20) |
| POST `/my-orders/{id}/cancel` | customer | TRK-18 |
| POST `/my-orders/requests/{id}/withdraw` | customer | TRK-21 |
| GET `/admin/changes` | admin | Customer changes list (also embedded at top of board) (TRK-24) |
| POST `/admin/changes/{id}/approve` · `/decline` · `/seen` | admin | TRK-22, TRK-25 |

The customer queries always include `WHERE customer_id = :me` inside the query helper itself, so a route can't forget it (TRK-16, AUTH-10). Customer JSON is built from a separate `CustomerOrderView` Pydantic model that has no `admin_note`, `phone` or history fields.

## UI notes
- Admin board cards: the big next-step button is thumb-sized, because the admin will often use a phone in the kitchen.
- The customer progress bar is 5 dots with labels. Cancelled orders replace the bar with a grey "Cancelled" badge.
- "Updated 10 minutes ago" is computed in the browser from an ISO timestamp, and recomputed on `visibilitychange` together with the data refresh.

## Tests
- State machine: every allowed and forbidden transition, undo window (frozen clock).
- `apply_draft` for new/update/cancel + the "already preparing" confirmation.
- Customer A can't see customer B's orders via the page or the JSON. No `admin_note` in customer responses.
- Prep list excludes cancelled orders.
- Customer edits: applied when `received`, requested when `confirmed`+, blocked when `delivered`/`cancelled`. Admin confirms between form open and save → becomes a request (TRK-23). A second request replaces the first; withdraw; approve/decline + reason visible to the customer. Customer can't edit another customer's order or change name/phone. Validation (no items, qty 0, past date). Diff output for item add/remove/change. Conflict flag with a chat draft (TRK-27).
