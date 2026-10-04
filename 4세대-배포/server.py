#!/usr/bin/env python3
"""Private Pokemon Generation IV Mystery Gift DLS server.

DNS requests are forwarded to a public Nintendo WFC replacement for NAS/SSL
authentication. Only the DLS host is overridden to this machine, so the gift
payload remains private and local.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import ipaddress
import logging
import os
import random
import signal
import socket
import socketserver
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import NamedTuple
from urllib.parse import parse_qs


LOGGER = logging.getLogger("gen4-distribution")
PCD_SIZE = 856
MYG_SIZE = 936
DEFAULT_DLS_HOSTS = {
    "conntest.nintendowifi.net",
    "dls1.nintendowifi.net",
    "dls2.nintendowifi.net",
    "dls1.nintendowifi.com",
    "dls2.nintendowifi.com",
    "dsdl.nintendowifi.net",
    "dsdl.nintendowifi.com",
    "a.dls1.wiimmfi.de",
    "dls1.wiimmfi.de",
    "dls2.wiimmfi.de",
    "dls1.riiconnect24.net",
    "dls2.riiconnect24.net",
    "dls1.pokeacer.xyz",
    "dls2.pokeacer.xyz",
    "dls2.pokeacer.tk",
}
WFC_DNS_SUFFIXES = (
    ".nintendowifi.net",
    ".nintendowifi.com",
    ".wiimmfi.de",
    ".riiconnect24.net",
    ".pokeacer.xyz",
    ".pokeacer.tk",
)


def is_wfc_name(name: str) -> bool:
    return name.endswith(WFC_DNS_SUFFIXES)


def is_local_distribution_name(name: str) -> bool:
    if name in DEFAULT_DLS_HOSTS:
        return True
    labels = name.split(".")
    return any(label == "dsdl" or label.startswith("dls") for label in labels)


def dns_query_details(query: bytes) -> tuple[str, int, str]:
    name, name_end = read_dns_name(query)
    if name_end + 4 > len(query):
        raise ValueError("truncated DNS question")
    qtype = struct.unpack("!H", query[name_end : name_end + 2])[0]
    return name, qtype, query[:2].hex()


def dns_response_details(response: bytes) -> tuple[int, int]:
    if len(response) < 12:
        raise ValueError("truncated DNS response")
    flags = struct.unpack("!H", response[2:4])[0]
    answers = struct.unpack("!H", response[6:8])[0]
    return flags & 0x000F, answers


def pcd_to_myg(data: bytes) -> bytes:
    """Convert a Generation IV PCD to the DLS MYG wire format."""
    if len(data) != PCD_SIZE:
        raise ValueError(f"PCD must be {PCD_SIZE} bytes; got {len(data)}")
    result = data[0x104:0x154] + data
    if len(result) != MYG_SIZE:
        raise AssertionError("internal MYG size error")
    return result


def read_dns_name(packet: bytes, offset: int = 12) -> tuple[str, int]:
    labels: list[str] = []
    while True:
        if offset >= len(packet):
            raise ValueError("truncated DNS name")
        length = packet[offset]
        offset += 1
        if length == 0:
            break
        if length & 0xC0:
            raise ValueError("compressed DNS question is unsupported")
        if offset + length > len(packet):
            raise ValueError("truncated DNS label")
        labels.append(packet[offset : offset + length].decode("ascii"))
        offset += length
    return ".".join(labels).lower(), offset


def make_local_dns_response(query: bytes, server_ip: str, hosts: set[str]) -> bytes | None:
    if len(query) < 12:
        return None
    qdcount = struct.unpack("!H", query[4:6])[0]
    if qdcount != 1:
        return None
    try:
        name, name_end = read_dns_name(query)
    except (UnicodeDecodeError, ValueError):
        return None
    if name_end + 4 > len(query):
        return None
    qtype, qclass = struct.unpack("!HH", query[name_end : name_end + 4])
    if name not in hosts or qclass != 1:
        return None

    question_end = name_end + 4
    request_flags = struct.unpack("!H", query[2:4])[0]
    flags = 0x8400 | (request_flags & 0x0100)  # response, authoritative, copy RD
    if qtype == 1:  # A
        header = query[:2] + struct.pack("!HHHHH", flags, 1, 1, 0, 0)
        answer = b"\xc0\x0c" + struct.pack(
            "!HHIH4s", 1, 1, 30, 4, socket.inet_aton(server_ip)
        )
        return header + query[12:question_end] + answer

    # Known local host, but no record of the requested type (for example AAAA).
    header = query[:2] + struct.pack("!HHHHH", flags, 1, 0, 0, 0)
    return header + query[12:question_end]


def forward_udp(query: bytes, upstream: tuple[str, int], timeout: float = 4.0) -> bytes:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(query, upstream)
        return sock.recvfrom(65535)[0]


class DnsState:
    def __init__(
        self,
        server_ip: str,
        upstream_ip: str,
        default_dns_ip: str,
        hosts: set[str],
    ):
        self.server_ip = server_ip
        self.upstream = (upstream_ip, 53)
        self.default_upstream = (default_dns_ip, 53)
        self.hosts = hosts

    def upstream_for(self, name: str) -> tuple[str, int]:
        if is_wfc_name(name):
            return self.upstream
        return self.default_upstream

    def resolve(self, query: bytes) -> bytes:
        try:
            name, qtype, transaction_id = dns_query_details(query)
        except (UnicodeDecodeError, ValueError):
            name = "<invalid>"
            qtype = -1
            transaction_id = query[:2].hex() if len(query) >= 2 else "none"
        is_nintendo = is_wfc_name(name)
        log = LOGGER.info if is_nintendo else LOGGER.debug
        log(
            "[NDS-DNS-01] query id=%s name=%s qtype=%d bytes=%d",
            transaction_id,
            name,
            qtype,
            len(query),
        )
        local = make_local_dns_response(query, self.server_ip, self.hosts)
        if local is not None:
            rcode, answers = dns_response_details(local)
            log(
                "[NDS-DNS-02] local-answer id=%s ip=%s rcode=%d answers=%d bytes=%d",
                transaction_id,
                self.server_ip,
                rcode,
                answers,
                len(local),
            )
            return local
        upstream = self.upstream_for(name)
        log("[NDS-DNS-03] upstream-send id=%s server=%s", transaction_id, upstream[0])
        started = time.monotonic()
        response = forward_udp(query, upstream)
        elapsed_ms = (time.monotonic() - started) * 1000
        rcode, answers = dns_response_details(response)
        log(
            "[NDS-DNS-04] upstream-reply id=%s rcode=%d answers=%d bytes=%d latency_ms=%.1f",
            transaction_id,
            rcode,
            answers,
            len(response),
            elapsed_ms,
        )
        return response


class ThreadingUdpServer(socketserver.ThreadingUDPServer):
    allow_reuse_address = True


class DnsUdpHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        query, sock = self.request
        try:
            response = self.server.state.resolve(query)
            sock.sendto(response, self.client_address)
            try:
                name, _, transaction_id = dns_query_details(query)
            except (UnicodeDecodeError, ValueError):
                name, transaction_id = "<invalid>", "none"
            if is_wfc_name(name):
                LOGGER.info(
                    "[NDS-DNS-05] udp-response-sent id=%s via_ics=%s:%d bytes=%d",
                    transaction_id,
                    self.client_address[0],
                    self.client_address[1],
                    len(response),
                )
        except Exception as exc:  # DS should time out instead of crashing the service
            LOGGER.error("[NDS-ERR-DNS-UDP] client=%s error=%s", self.client_address[0], exc)


class ThreadingTcpServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


class DnsTcpHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        length_data = self.request.recv(2)
        if len(length_data) != 2:
            return
        wanted = struct.unpack("!H", length_data)[0]
        chunks = bytearray()
        while len(chunks) < wanted:
            part = self.request.recv(wanted - len(chunks))
            if not part:
                return
            chunks.extend(part)
        try:
            response = self.server.state.resolve(bytes(chunks))
            self.request.sendall(struct.pack("!H", len(response)) + response)
            try:
                name, _, transaction_id = dns_query_details(bytes(chunks))
            except (UnicodeDecodeError, ValueError):
                name, transaction_id = "<invalid>", "none"
            if is_wfc_name(name):
                LOGGER.info(
                    "[NDS-DNS-05] tcp-response-sent id=%s via_ics=%s bytes=%d",
                    transaction_id,
                    self.client_address[0],
                    len(response),
                )
        except Exception as exc:
            LOGGER.error("DNS TCP request failed from %s: %s", self.client_address[0], exc)


class GiftFile(NamedTuple):
    filename: str
    myg: bytes
    source: Path


def load_gift_directory(directory: Path) -> list[GiftFile]:
    """Load every valid PCD in a directory using ASCII-safe DLS filenames."""
    directory = directory.resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"gift directory does not exist: {directory}")
    paths = sorted(
        (path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".pcd"),
        key=lambda path: path.name.casefold(),
    )
    if not paths:
        raise FileNotFoundError(f"no PCD files found in gift directory: {directory}")

    gifts = []
    for index, path in enumerate(paths, start=1):
        try:
            myg = pcd_to_myg(path.read_bytes())
        except ValueError as exc:
            raise ValueError(f"invalid PCD file {path.name}: {exc}") from exc
        gifts.append(GiftFile(f"private-gift-{index:03d}.myg", myg, path))
    return gifts


class GiftState:
    def __init__(self, gifts: list[GiftFile], server_ip: str):
        if not gifts:
            raise ValueError("at least one gift is required")
        self.gifts = tuple(gifts)
        self.server_ip = server_ip
        self._by_filename = {gift.filename: gift for gift in gifts}
        self._selected: dict[str, GiftFile] = {}
        self._lock = threading.Lock()
        self._random = random.SystemRandom()

    def choose(self, client_ip: str) -> GiftFile:
        gift = self._random.choice(self.gifts)
        with self._lock:
            self._selected[client_ip] = gift
        return gift

    def selected(self, client_ip: str, filename: str) -> GiftFile | None:
        with self._lock:
            gift = self._selected.get(client_ip)
        if gift is not None and gift.filename == filename:
            return gift
        return None


def decode_dls_value(value: str) -> str:
    """Decode Nintendo DLS' modified Base64 form while retaining plain input."""
    if value.lower() in {"count", "list", "contents"}:
        return value
    encoded = (
        value.replace("*", "=")
        .replace("?", "/")
        .replace(">", "+")
        .replace("-", "/")
    )
    try:
        return base64.b64decode(encoded, validate=True).decode("ascii")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return value


class GiftHandler(BaseHTTPRequestHandler):
    server_version = "Nintendo Wii (http)"
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        LOGGER.debug("HTTP %s - %s", self.client_address[0], fmt % args)

    def do_GET(self) -> None:
        LOGGER.info(
            "[NDS-HTTP-01] connection-test-request client=%s path=%s user_agent=%s",
            self.client_address[0],
            self.path,
            self.headers.get("User-Agent", "-"),
        )
        body = b"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN">
<html><head><title>HTML Page</title></head>
<body bgcolor="#FFFFFF">This is test.html page</body></html>
"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        LOGGER.info("[NDS-HTTP-02] connection-test-response status=200 bytes=%d", len(body))

    def do_POST(self) -> None:
        if self.path != "/download":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("ascii", "replace")
            values = parse_qs(raw, keep_blank_values=True)
            encoded_post = {key: items[-1] for key, items in values.items()}
            post = {key: decode_dls_value(value) for key, value in encoded_post.items()}
            encoded_action = encoded_post.get("action", "")
            action = post.get("action", "").lower()
            game = post.get("gamecd", "unknown")
            LOGGER.info(
                "[NDS-DLS-01] request action=%s encoded_action=%s game=%s bytes=%d",
                action,
                encoded_action,
                game,
                length,
            )

            if action == "count":
                body = b"1"
                content_type = "text/plain"
            elif action == "list":
                gift = self.server.state.choose(self.client_address[0])
                line = f"{gift.filename}\t\t\t\t\t{MYG_SIZE}\r\n"
                body = line.encode("ascii")
                content_type = "text/plain"
                LOGGER.info(
                    "[NDS-GIFT-SELECT] client=%s selected=%s source=%s pool=%d",
                    self.client_address[0],
                    gift.filename,
                    gift.source.name,
                    len(self.server.state.gifts),
                )
            elif action == "contents":
                requested = os.path.basename(post.get("contents", ""))
                gift = self.server.state.selected(self.client_address[0], requested)
                if gift is None:
                    self.send_error(404, "Unknown gift")
                    return
                body = gift.myg
                content_type = "application/x-dsdl"
            else:
                body = b""
                content_type = "text/plain"

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-DLS-Host", f"http://{self.server.state.server_ip}/")
            if action == "contents":
                self.send_header(
                    "Content-Disposition",
                    f'attachment; filename="{requested}"',
                )
            self.end_headers()
            self.wfile.write(body)
            LOGGER.info("[NDS-DLS-02] response action=%s status=200 bytes=%d", action, len(body))
        except Exception as exc:
            LOGGER.exception("DLS request failed: %s", exc)
            self.send_error(500)


def valid_ipv4(value: str) -> str:
    parsed = ipaddress.ip_address(value)
    if parsed.version != 4 or parsed.is_loopback or parsed.is_unspecified:
        raise argparse.ArgumentTypeError("a non-loopback IPv4 address is required")
    return str(parsed)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-ip", required=True, type=valid_ipv4)
    parser.add_argument(
        "--bind-ip",
        type=valid_ipv4,
        help="local address to bind; defaults to --server-ip",
    )
    parser.add_argument("--pcd", default="gift.pcd", type=Path)
    parser.add_argument("--upstream-dns", default="167.235.229.36", type=valid_ipv4)
    parser.add_argument("--default-dns", default="1.1.1.1", type=valid_ipv4)
    parser.add_argument("--dns-port", default=53, type=int)
    parser.add_argument("--http-port", default=80, type=int)
    parser.add_argument("--log-file", default="diagnostics.log", type=Path)
    parser.add_argument(
        "--http-only",
        action="store_true",
        help="run only the DLS HTTP server (diagnostics only)",
    )
    parser.add_argument(
        "--dns-only",
        action="store_true",
        help="run only the DNS server",
    )
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.http_only and args.dns_only:
        raise SystemExit("--http-only and --dns-only cannot be used together")
    bind_ip = args.bind_ip or args.server_ip
    log_file = args.log_file.resolve()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=(
            logging.StreamHandler(),
            logging.FileHandler(log_file, mode="w", encoding="utf-8"),
        ),
    )
    LOGGER.info(
        "[BOOT-01] bind_ip=%s advertised_ip=%s dns_port=%d http_port=%d log=%s",
        bind_ip,
        args.server_ip,
        args.dns_port,
        args.http_port,
        log_file,
    )
    pcd_path = args.pcd.resolve()
    try:
        myg = pcd_to_myg(pcd_path.read_bytes())
    except (OSError, ValueError) as exc:
        LOGGER.error("Cannot load gift card %s: %s", pcd_path, exc)
        return 2

    output = pcd_path.with_suffix(".myg")
    output.write_bytes(myg)
    LOGGER.info("Gift ready: %s (%d-byte PCD -> %d-byte MYG)", pcd_path.name, PCD_SIZE, len(myg))

    servers: list[socketserver.BaseServer] = []
    if not args.dns_only:
        gift_state = GiftState(myg, "private-gift.myg", args.server_ip)
        http_server = ThreadingHTTPServer((bind_ip, args.http_port), GiftHandler)
        http_server.state = gift_state
        servers.append(http_server)

    if not args.http_only:
        dns_state = DnsState(
            args.server_ip,
            args.upstream_dns,
            args.default_dns,
            DEFAULT_DLS_HOSTS,
        )
        udp_server = ThreadingUdpServer((bind_ip, args.dns_port), DnsUdpHandler)
        tcp_server = ThreadingTcpServer((bind_ip, args.dns_port), DnsTcpHandler)
        udp_server.state = tcp_server.state = dns_state
        servers.extend((udp_server, tcp_server))
    threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in servers]
    for thread in threads:
        thread.start()

    if not args.http_only:
        LOGGER.info("DNS listening on %s UDP/TCP %d", bind_ip, args.dns_port)
    if not args.dns_only:
        LOGGER.info("DLS listening on %s HTTP %d", bind_ip, args.http_port)
    LOGGER.info("Set the DS primary and secondary DNS to %s", args.server_ip)
    if not args.dns_only and bind_ip != args.server_ip:
        try:
            started = time.monotonic()
            with socket.create_connection((args.server_ip, args.http_port), timeout=5) as sock:
                sock.sendall(
                    b"GET /health HTTP/1.0\r\n"
                    + f"Host: {args.server_ip}\r\n".encode("ascii")
                    + b"User-Agent: gen4-self-test\r\n\r\n"
                )
                status_line = sock.recv(128).split(b"\r\n", 1)[0]
            LOGGER.info(
                "[SELFTEST-HTTP-PASS] target=%s:%d status=%s latency_ms=%.1f",
                args.server_ip,
                args.http_port,
                status_line.decode("ascii", "replace"),
                (time.monotonic() - started) * 1000,
            )
        except OSError as exc:
            LOGGER.error(
                "[SELFTEST-HTTP-FAIL] target=%s:%d error=%s",
                args.server_ip,
                args.http_port,
                exc,
            )
    LOGGER.info("Press Ctrl+C to stop")
    stop = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    stop.wait()
    for server in servers:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

