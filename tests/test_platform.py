"""001 Platform."""

import re
import shutil
from pathlib import Path

from app import banner
from order_taker import db
from order_taker.config import Settings

from .conftest import login_admin, page_text, setup_admin

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "order_taker" / "web"


def test_plt1_plt2_banner_shows_laptop_and_wifi_urls():
    """PLT-1, PLT-2: plain-English start message with both addresses."""
    text = banner(8000, "192.168.1.23")
    assert "http://127.0.0.1:8000" in text
    assert "http://192.168.1.23:8000" in text
    assert "Wi-Fi" in text


def test_plt3_database_created_with_tables(settings, app):
    """PLT-3: one SQLite file, created with its tables on first start."""
    assert Path(settings.db_path).exists()
    conn = db.connect(settings.db_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"users", "orders", "order_items", "drafts", "status_history", "seen_messages", "settings"} <= tables


def test_plt4_migrations_are_idempotent_and_upgrade_in_place(tmp_path):
    """PLT-4: re-running is a no-op; a new numbered file applies without losing data."""
    mig = tmp_path / "mig"
    shutil.copytree(db.MIGRATIONS_DIR, mig)
    conn = db.connect(str(tmp_path / "x.db"))
    v = db.migrate(conn, mig)
    conn.execute("INSERT INTO settings (key, value) VALUES ('shop_name', 'Keep me')")
    assert db.migrate(conn, mig) == v
    (mig / f"{v + 1:04d}_extra.sql").write_text("ALTER TABLE orders ADD COLUMN extra TEXT DEFAULT ''")
    assert db.migrate(conn, mig) == v + 1
    assert db.get_setting(conn, "shop_name") == "Keep me"
    assert "extra" in [r[1] for r in conn.execute("PRAGMA table_info(orders)")]


def test_plt5_settings_from_env(monkeypatch):
    """PLT-5: defaults, overridable by env vars."""
    for k in ("ORDER_MODEL", "ORDER_SORTER_MODEL", "OLLAMA_URL", "ORDER_PARALLEL"):
        monkeypatch.delenv(k, raising=False)
    s = Settings()
    assert (s.model, s.sorter_model, s.ollama_url, s.parallel) == (
        "qwen2.5:7b", "qwen2.5:3b", "http://localhost:11434", 3)
    monkeypatch.setenv("ORDER_MODEL", "llama3.2")
    monkeypatch.setenv("ORDER_PARALLEL", "5")
    s = Settings()
    assert s.model == "llama3.2" and s.parallel == 5


def test_plt6_works_without_ollama_and_intake_explains(client, fake):
    """PLT-6: pages work when Ollama is down; intake shows the plain-English message."""
    fake.up = False
    setup_admin(client)
    assert client.get("/admin").status_code == 200
    page = page_text(client.get("/admin/intake"))
    assert "The AI helper isn't running. Open the Ollama app and try again." in page


def test_plt7_no_external_resources():
    """PLT-7: every script and stylesheet is served by the app itself."""
    for tpl in (WEB / "templates").glob("*.html"):
        html = tpl.read_text(encoding="utf-8")
        for tag in re.findall(r"<(?:script|link)[^>]*>", html):
            assert "http" not in tag, f"{tpl.name}: {tag}"
    css = (WEB / "static" / "app.css").read_text(encoding="utf-8")
    assert "@import" not in css and "url(http" not in css


def test_plt8_data_and_chats_ignored_by_git():
    """PLT-8."""
    lines = (ROOT / ".gitignore").read_text().splitlines()
    assert "data/" in lines and "chats/" in lines


def test_plt9_csv_export(client, conn):
    """PLT-9 / TRK-9: CSV of the orders shown."""
    from .conftest import make_customer, make_order
    setup_admin(client)
    login_admin(client)
    make_order(conn, make_customer(conn), delivery_date="2099-01-05")
    r = client.get("/admin/orders.csv?tab=upcoming")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "1 kg chocolate cake" in r.text and "Priya" in r.text
