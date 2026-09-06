from __future__ import annotations

import ipaddress
import socket
import struct
import threading
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor

from .packet_log import PacketLog


def parse_question(packet: bytes) -> tuple[str, int, int]:
    if len(packet) < 17:
        raise ValueError("DNS packet is too short")
    labels: list[str] = []
    offset = 12
    while True:
        if offset >= len(packet):
            raise ValueError("unterminated DNS name")
        length = packet[offset]
        offset += 1
        if length == 0:
            break
        if length & 0xC0:
            raise ValueError("compressed questions are not supported")
        if offset + length > len(packet):
            raise ValueError("truncated DNS label")
        labels.append(packet[offset:offset + length].decode("ascii", errors="replace"))
        offset += length
    if offset + 4 > len(packet):
        raise ValueError("truncated DNS question type")
    qtype, qclass = struct.unpack_from("!HH", packet, offset)
    if qclass != 1:
        raise ValueError("only Internet-class DNS is supported")
    return ".".join(labels).lower().rstrip("."), qtype, offset + 4


def build_a_response(query: bytes, question_end: int, address: str) -> bytes:
    ip = ipaddress.ip_address(address)
    if ip.version != 4:
        raise ValueError("Nintendo DS overrides require an IPv4 address")
    transaction_id = query[:2]
    flags = b"\x81\x80"
    counts = struct.pack("!HHHH", 1, 1, 0, 0)
    question = query[12:question_end]
    answer = b"\xC0\x0C" + struct.pack("!HHIH", 1, 1, 60, 4) + ip.packed
    return transaction_id + flags + counts + question + answer


class DnsProxy:
    def __init__(
        self,
        bind_ip: str,
        port: int,
        target_ip: str,
        override_domains: Iterable[str],
        upstream_ip: str,
        upstream_port: int,
        packet_log: PacketLog,
        fixed_records: dict[str, str] | None = None,
    ) -> None:
        self.bind_ip = bind_ip
        self.port = port
        self.target_ip = target_ip
        self.override_domains = {domain.lower().rstrip(".") for domain in override_domains}
        self.upstream = (upstream_ip, upstream_port)
        self.packet_log = packet_log
        self.fixed_records = {name.lower().rstrip("."): str(ipaddress.IPv4Address(value))
                              for name, value in (fixed_records or {}).items()}
        self.socket: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._forward_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="dns-forward")
        self._forward_slots = threading.BoundedSemaphore(32)

    def start(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.bind_ip, self.port))
        sock.settimeout(0.5)
        self.socket = sock
        self.thread = threading.Thread(target=self._serve, name="ds-dns", daemon=True)
        self.thread.start()

    def close(self) -> None:
        self._stop.set()
        self._forward_pool.shutdown(wait=False, cancel_futures=True)
        if self.socket:
            self.socket.close()

    def _forward(self, packet: bytes) -> bytes | None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as upstream:
            upstream.settimeout(3)
            upstream.sendto(packet, self.upstream)
            try:
                return upstream.recvfrom(4096)[0]
            except TimeoutError:
                return None

    def _forward_to_client(self, packet: bytes, client: tuple[str, int]) -> None:
        try:
            response = self._forward(packet)
            if response and self.socket and not self._stop.is_set():
                self.socket.sendto(response, client)
        except OSError as exc:
            if not self._stop.is_set():
                self.packet_log.write("dns_error", client=client[0], error=str(exc))
        finally:
            self._forward_slots.release()

    def _serve(self) -> None:
        assert self.socket is not None
        while not self._stop.is_set():
            try:
                packet, client = self.socket.recvfrom(4096)
            except (TimeoutError, OSError):
                continue
            try:
                domain, qtype, question_end = parse_question(packet)
                overridden = domain in self.override_domains and qtype == 1
                answer_ip = self.target_ip if overridden else self.fixed_records.get(domain) if qtype == 1 else None
                self.packet_log.write(
                    "dns", raw=packet, client=client[0], domain=domain,
                    qtype=qtype, overridden=overridden, answer_ip=answer_ip,
                )
                if answer_ip:
                    self.socket.sendto(build_a_response(packet, question_end, answer_ip), client)
                elif self._forward_slots.acquire(blocking=False):
                    try:
                        self._forward_pool.submit(self._forward_to_client, packet, client)
                    except RuntimeError:
                        self._forward_slots.release()
            except Exception as exc:  # malformed client packets must not stop DNS
                self.packet_log.write("dns_error", raw=packet, client=client[0], error=str(exc))
