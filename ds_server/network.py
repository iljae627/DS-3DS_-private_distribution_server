from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable


WINDOWS_HOTSPOT_IP = "192.168.137.1"


def choose_server_ip(addresses: Iterable[str], routed_ip: str | None = None) -> str:
    """Pick the address a DS should use, preferring an active Windows hotspot."""
    usable: list[str] = []
    for value in addresses:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            continue
        if address.version != 4 or address.is_loopback or address.is_link_local:
            continue
        usable.append(str(address))

    if WINDOWS_HOTSPOT_IP in usable:
        return WINDOWS_HOTSPOT_IP
    if routed_ip in usable:
        return str(routed_ip)
    if usable:
        return usable[0]
    raise OSError("사용 가능한 로컬 IPv4 주소를 찾지 못했습니다.")


def detect_server_ip(upstream: str) -> str:
    """Detect an active LAN/hotspot IPv4 without inventing an inactive address."""
    candidates: list[str] = []
    try:
        candidates.extend(
            item[4][0]
            for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
        )
    except OSError:
        pass

    routed_ip: str | None = None
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect((upstream, 53))
            routed_ip = sock.getsockname()[0]
            candidates.append(routed_ip)
        except OSError:
            pass

    return choose_server_ip(candidates, routed_ip)
