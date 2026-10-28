#!/usr/bin/env python3
"""Private Pokemon Generation V Mystery Gift DLS implementation."""

from __future__ import annotations

import binascii
import importlib.util
import logging
import os
import random
import sys
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import NamedTuple
from urllib.parse import parse_qs


_GEN4_PATH = Path(__file__).resolve().parent.parent / "4세대-배포" / "server.py"
_SPEC = importlib.util.spec_from_file_location("gen4_network_base", _GEN4_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"4세대 공통 네트워크 모듈을 불러올 수 없습니다: {_GEN4_PATH}")
_BASE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _BASE
_SPEC.loader.exec_module(_BASE)

# DNS, HTTP server and validation helpers are shared with the proven Gen IV server.
DEFAULT_DLS_HOSTS = _BASE.DEFAULT_DLS_HOSTS
WFC_DNS_SUFFIXES = _BASE.WFC_DNS_SUFFIXES
ThreadingHTTPServer = _BASE.ThreadingHTTPServer
is_wfc_name = _BASE.is_wfc_name
is_local_distribution_name = _BASE.is_local_distribution_name
dns_query_details = _BASE.dns_query_details
dns_response_details = _BASE.dns_response_details
make_local_dns_response = _BASE.make_local_dns_response
forward_udp = _BASE.forward_udp
valid_ipv4 = _BASE.valid_ipv4
decode_dls_value = _BASE.decode_dls_value

LOGGER = logging.getLogger("gen5-distribution")
_BASE.LOGGER = LOGGER

PGF_SIZE = 0xCC
WIRE_SIZE = 0x2D0
MAX_CARD_ID = 2047
# windows_server.py inherited from Gen IV logs this compatibility name.
MYG_SIZE = WIRE_SIZE

LANGUAGE_BY_ATTR = {
    "J": 1,
    "E": 2,
    "F": 3,
    "D": 4,
    "I": 5,
    "S": 7,
    "K": 8,
}

# rhgamecd's third character identifies Black, White, Black 2, or White 2.
RH_GAME_BIT = {"A": 0x10, "B": 0x20, "D": 0x40, "E": 0x80}


def crc16_ccitt(data: bytes) -> int:
    """Nintendo WC5FULL CRC-16/CCITT (initial value 0xffff)."""
    return binascii.crc_hqx(data, 0xFFFF)


def pgf_to_wire(
    data: bytes,
    *,
    language: int = 8,
    game_flags: int = 0x00F0,
    message: str = "이상한 소포가 도착했습니다!",
) -> bytes:
    """Wrap a 204-byte PGF in the 720-byte Generation V DLS format."""
    if len(data) != PGF_SIZE:
        raise ValueError(f"PGF must be {PGF_SIZE} bytes; got {len(data)}")
    if language not in LANGUAGE_BY_ATTR.values():
        raise ValueError(f"unsupported language flag: {language}")
    if not 0 <= game_flags <= 0xFFFF:
        raise ValueError("game flags must fit in 16 bits")

    result = bytearray(b"\xFF" * WIRE_SIZE)
    result[:PGF_SIZE] = data
    result[0xCC:0xCE] = b"\x00\x00"
    result[0xCE:0xD0] = game_flags.to_bytes(2, "little")

    encoded = message.encode("utf-16le") + b"\xFF\xFF"
    if len(encoded) > 0x1FA:
        raise ValueError("distribution message is too long")
    result[0xD0 : 0xD0 + len(encoded)] = encoded
    result[0x2CA] = 0  # standard download animation
    result[0x2CB] = language
    result[0x2CC:0x2CE] = b"\x00\x00"
    result[0x2CE:0x2D0] = crc16_ccitt(result[:0x2CE]).to_bytes(2, "little")
    return bytes(result)


class GiftFile(NamedTuple):
    filename: str
    myg: bytes
    source: Path
    language: int
    game_flags: int


def load_gift_directory(directory: Path) -> list[GiftFile]:
    """Load PGF templates or exact WC5FULL files; source names are not sent."""
    directory = directory.resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"gift directory does not exist: {directory}")
    paths = sorted(
        (p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in {".pgf", ".wc5full"}),
        key=lambda p: p.name.casefold(),
    )
    if not paths:
        raise FileNotFoundError(f"no PGF or WC5FULL files found in gift directory: {directory}")

    gifts: list[GiftFile] = []
    for index, path in enumerate(paths, start=1):
        try:
            data = path.read_bytes()
            if path.suffix.lower() == ".wc5full":
                if len(data) != WIRE_SIZE:
                    raise ValueError(f"WC5FULL must be {WIRE_SIZE} bytes; got {len(data)}")
                expected = int.from_bytes(data[0x2CE:0x2D0], "little")
                actual = crc16_ccitt(data[:0x2CE])
                if expected != actual:
                    raise ValueError(f"WC5FULL CRC mismatch: stored {expected:04X}, calculated {actual:04X}")
                language = data[0x2CB]
                if language not in LANGUAGE_BY_ATTR.values():
                    raise ValueError(f"unsupported WC5FULL language flag: {language}")
                # Preserve the original restriction bytes on the wire. Selection
                # remains broad because Korean rhgamecd values do not map cleanly
                # to the WC5FULL low-byte flag positions.
                game_flags = 0x00F0
                wire = data
                pgf = data[:PGF_SIZE]
            else:
                if len(data) != PGF_SIZE:
                    raise ValueError(f"PGF must be {PGF_SIZE} bytes; got {len(data)}")
                language = 8
                game_flags = 0x00F0
                wire = pgf_to_wire(data, language=language, game_flags=game_flags)
                pgf = data

            card_id = int.from_bytes(pgf[0xB0:0xB2], "little")
            if not 1 <= card_id <= MAX_CARD_ID:
                raise ValueError(f"Generation V card ID must be 1-{MAX_CARD_ID}; got {card_id}")
            if pgf[0xB3] != 1:
                raise ValueError(f"unsupported Generation V card type: {pgf[0xB3]} (expected Pokemon type 1)")
            if pgf[0xB4] != 1:
                raise ValueError(f"Generation V Wi-Fi card status must be 1 (new/unreceived); got {pgf[0xB4]}")
        except ValueError as exc:
            raise ValueError(f"invalid Generation V gift file {path.name}: {exc}") from exc
        gifts.append(GiftFile(f"private-gift-{index:03d}.bin", wire, path, language, game_flags))
    return gifts


class GiftState:
    def __init__(self, gifts: list[GiftFile], server_ip: str):
        if not gifts:
            raise ValueError("at least one gift is required")
        self.gifts = tuple(gifts)
        self.server_ip = server_ip
        self._selected: dict[str, GiftFile] = {}
        self._lock = threading.Lock()
        self._random = random.SystemRandom()

    def choose(self, client_ip: str, language: int | None, game_bit: int | None) -> GiftFile | None:
        candidates = [
            gift for gift in self.gifts
            if (language is None or gift.language == language)
            and (game_bit is None or gift.game_flags & game_bit)
        ]
        if not candidates:
            return None
        gift = self._random.choice(candidates)
        with self._lock:
            self._selected[client_ip] = gift
        return gift

    def selected(self, client_ip: str, filename: str) -> GiftFile | None:
        with self._lock:
            gift = self._selected.get(client_ip)
        return gift if gift is not None and gift.filename == filename else None


def request_filters(post: dict[str, str]) -> tuple[int | None, int | None]:
    attr1 = post.get("attr1", "").upper()
    language = LANGUAGE_BY_ATTR.get(attr1.rsplit("_", 1)[-1]) if attr1.startswith("MYSTERY_") else None
    rhgamecd = post.get("rhgamecd", "").upper()
    game_bit = RH_GAME_BIT.get(rhgamecd[2]) if len(rhgamecd) >= 3 else None
    return language, game_bit


class GiftHandler(BaseHTTPRequestHandler):
    server_version = "Nintendo Wii (http)"
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        LOGGER.debug("HTTP %s - %s", self.client_address[0], fmt % args)

    def do_GET(self) -> None:
        body = b"<html><body>This is test.html page</body></html>\r\n"
        LOGGER.info("[NDS5-HTTP-01] connection-test client=%s path=%s", self.client_address[0], self.path)
        self._reply(body, "text/html")

    def do_POST(self) -> None:
        if self.path != "/download":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("ascii", "replace")
            encoded = {k: v[-1] for k, v in parse_qs(raw, keep_blank_values=True).items()}
            post = {k: decode_dls_value(v) for k, v in encoded.items()}
            action = post.get("action", "").lower()
            language, game_bit = request_filters(post)
            LOGGER.info(
                "[NDS5-DLS-01] action=%s game=%s rhgame=%s attr1=%s",
                action, post.get("gamecd", "unknown"), post.get("rhgamecd", "-"), post.get("attr1", "-"),
            )

            if action in {"count", "list"}:
                gift = self.server.state.choose(self.client_address[0], language, game_bit)
                if action == "count":
                    body = b"1" if gift is not None else b"0"
                elif gift is None:
                    body = b"\r\n"
                else:
                    attr_suffix = next((k for k, v in LANGUAGE_BY_ATTR.items() if v == gift.language), "K")
                    # filename, hash, content type, game bit mask, reserved, size
                    body = f"{gift.filename}\t\tMYSTERY_{attr_suffix}\tF00000\t\t{WIRE_SIZE}\r\n".encode("ascii")
                    LOGGER.info("[NDS5-GIFT-SELECT] client=%s wire=%s source=%s", self.client_address[0], gift.filename, gift.source.name)
                self._reply(body, "text/plain")
            elif action == "contents":
                requested = os.path.basename(post.get("contents", ""))
                gift = self.server.state.selected(self.client_address[0], requested)
                if gift is None:
                    self.send_error(404, "Unknown gift")
                    return
                self._reply(gift.myg, "application/x-dsdl", requested)
            else:
                self._reply(b"", "text/plain")
        except Exception as exc:
            LOGGER.exception("Generation V DLS request failed: %s", exc)
            self.send_error(500)

    def _reply(self, body: bytes, content_type: str, filename: str | None = None) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-DLS-Host", f"http://{self.server.state.server_ip}/")
        if filename is not None:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)
        LOGGER.info("[NDS5-DLS-02] status=200 bytes=%d", len(body))

