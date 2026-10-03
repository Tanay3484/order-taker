"""Start Order Taker: python app.py (PLT-1, PLT-2)."""

from __future__ import annotations

import logging

import uvicorn

from order_taker.config import get_settings
from order_taker.web.main import create_app
from order_taker.web.net import lan_ip


def banner(port: int, ip: str) -> str:
    return (
        "\nOrder Taker is running.\n"
        f"  On this laptop:          http://127.0.0.1:{port}\n"
        f"  On phones (same Wi-Fi):  http://{ip}:{port}\n"
        "Press Ctrl+C to stop.\n"
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    app = create_app(settings)
    print(banner(settings.port, lan_ip()), flush=True)
    uvicorn.run(app, host="0.0.0.0", port=settings.port, log_level="warning")


if __name__ == "__main__":
    main()
