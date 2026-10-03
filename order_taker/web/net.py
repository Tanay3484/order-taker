"""Find this laptop's address on the local network (PLT-2)."""

from __future__ import annotations

import socket


def lan_ip() -> str:
    # Connecting a UDP socket sends no packets; it just picks the outgoing interface.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            if not ip.startswith("127."):
                return ip
    except OSError:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"
