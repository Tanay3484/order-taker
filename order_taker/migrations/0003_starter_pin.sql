-- AUTH-13: the shop-issued PIN, readable until the customer chooses their own
ALTER TABLE users ADD COLUMN starter_pin TEXT;
