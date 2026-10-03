CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    role TEXT NOT NULL CHECK (role IN ('admin', 'customer')),
    phone TEXT UNIQUE,
    username TEXT UNIQUE,
    name TEXT NOT NULL DEFAULT '',
    pin_hash TEXT NOT NULL,
    must_change_pin INTEGER NOT NULL DEFAULT 0,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES users(id),
    customer_name TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    delivery_date TEXT NOT NULL DEFAULT '',
    delivery_time TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'received',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX orders_customer ON orders(customer_id);
CREATE INDEX orders_date ON orders(delivery_date);

CREATE TABLE order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    quantity REAL NOT NULL,
    unit TEXT NOT NULL DEFAULT ''
);

CREATE TABLE status_history (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    prev_status TEXT,
    note TEXT NOT NULL DEFAULT '',
    changed_by INTEGER REFERENCES users(id),
    at TEXT NOT NULL
);

CREATE TABLE intake_runs (
    id INTEGER PRIMARY KEY,
    started_by INTEGER REFERENCES users(id),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    summary TEXT NOT NULL DEFAULT ''
);

CREATE TABLE drafts (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL CHECK (source IN ('chat', 'customer')),
    run_id INTEGER REFERENCES intake_runs(id),
    requested_by INTEGER REFERENCES users(id),
    sender TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL CHECK (action IN ('new', 'update', 'cancel', 'question')),
    target_order_id INTEGER REFERENCES orders(id),
    payload_json TEXT NOT NULL DEFAULT '{}',
    before_json TEXT,
    flags_json TEXT NOT NULL DEFAULT '[]',
    raw_text TEXT NOT NULL DEFAULT '',
    decline_reason TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'accepted', 'discarded', 'declined', 'withdrawn', 'applied')),
    seen_by_customer INTEGER NOT NULL DEFAULT 0,
    seen_by_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    decided_at TEXT
);
CREATE INDEX drafts_target ON drafts(target_order_id, state);

CREATE TABLE seen_messages (
    hash TEXT PRIMARY KEY,
    run_id INTEGER REFERENCES intake_runs(id),
    sender TEXT NOT NULL,
    sent_at TEXT
);
