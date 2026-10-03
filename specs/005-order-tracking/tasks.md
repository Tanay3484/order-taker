# 005 Order Tracking: Tasks

- [x] T1. Migration 0002: `settings`, `orders.admin_note`
- [x] T2. `orders.py` state machine + history + undo + tests (TRK-4, TRK-5, TRK-6)
- [x] T3. `apply_draft` for new/update/cancel incl. confirm-if-preparing; call `ensure_customer` (TRK-1, TRK-2, TRK-3, AUTH-4)
- [x] T4. Admin board with tabs + order cards + next-step button (TRK-7, TRK-8)
- [x] T5. Prep list per day + CSV export (TRK-9)
- [x] T6. Customers list with Reset PIN; Settings page; shop details on setup (TRK-10, TRK-11)
- [x] T7. Customer `/my-orders` page + JSON, progress bar, past orders, WhatsApp link, refresh on focus (TRK-12..15)
- [x] T8. Isolation tests: cross-customer access and admin_note leakage (TRK-16)
- [x] T9. `orders.diff()` + `customer_change()` with status-based apply vs request, inside `BEGIN IMMEDIATE` (TRK-17, TRK-19, TRK-20, TRK-23)
- [x] T10. Customer edit form (item rows, date min, pickup toggle) + cancel with confirm step (TRK-17, TRK-18)
- [x] T11. Pending-request display on customer order, withdraw, approved/declined messages (TRK-20, TRK-21, TRK-22)
- [x] T12. Admin "Customer changes" section + nav badge + approve/decline/seen + board badges (TRK-24, TRK-25, TRK-26)
- [x] T13. Conflict flag between chat draft and customer request; history entries (TRK-27, TRK-28)
- [x] T14. Login info on order cards and the customers list (TRK-8, TRK-10)
- [x] T15. Warm bakery palette + dark mode in `app.css`
- [x] T16. Phone editable on Edit order, relinking the customer (TRK-29)
