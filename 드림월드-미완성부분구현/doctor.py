#!/usr/bin/env python3
"""Pre-flight checks that do not require an existing Game Sync save."""

from __future__ import annotations

import importlib.util
import socket
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def check(label: str, ok: bool, detail: str = "") -> bool:
    mark = "OK" if ok else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"[{mark}] {label}{suffix}")
    return ok


def port_available(port: int, sock_type: int) -> bool:
    sock = socket.socket(socket.AF_INET, sock_type)
    try:
        # dnslib's UDP server uses address reuse on Windows as well.
        if sock_type == socket.SOCK_DGRAM:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def main() -> int:
    results = []
    results.append(check("Python 3.10+", sys.version_info >= (3, 10), sys.version.split()[0]))
    for package in ("flask", "tzdata", "dnslib", "tlslite", "cryptography"):
        results.append(check(f"Python package: {package}", importlib.util.find_spec(package) is not None))

    assets = ROOT / "dreamworld_assets" / "shared.pokemon-gl.com"
    sync_server = ROOT / "game_sync_server" / "server.py"
    results.append(check("Dream World assets", assets.is_dir()))
    results.append(check("Game Sync submodule", sync_server.is_file()))

    for port, sock_type, name in (
        (53, socket.SOCK_DGRAM, "DNS/UDP 53"),
        (80, socket.SOCK_STREAM, "HTTP/TCP 80"),
        (443, socket.SOCK_STREAM, "HTTPS/TCP 443"),
        (29900, socket.SOCK_STREAM, "GameSpy/TCP 29900"),
        (8080, socket.SOCK_STREAM, "Dream World/TCP 8080"),
    ):
        results.append(check(f"Port available: {name}", port_available(port, sock_type)))

    if all(results):
        print("\nPre-flight checks passed.")
        return 0
    print("\nOne or more checks failed. Close the program using the port and retry.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
