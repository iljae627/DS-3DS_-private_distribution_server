from __future__ import annotations

import argparse
import ipaddress
import shutil
import struct
from pathlib import Path

from ds_server.network import detect_server_ip


ROOT = Path(__file__).resolve().parent
PROFILE_SIZE = 0x100
EXTENDED_PROFILE_SIZE = 0x200
WFC_SETTINGS_SIZE = 3 * (PROFILE_SIZE + EXTENDED_PROFILE_SIZE)


def melon_crc16(data: bytes, start: int = 0) -> int:
    """Nintendo DS firmware CRC16, matching melonDS SPI.cpp."""
    lookup = (0xC0C1, 0xC181, 0xC301, 0xC601, 0xCC01, 0xD801, 0xF001, 0xA001)
    value = start
    for byte in data:
        value ^= byte
        for bit in range(8):
            if value & 1:
                value = (value >> 1) ^ ((lookup[bit] << (7 - bit)) & 0xFFFF)
            else:
                value >>= 1
    return value & 0xFFFF


def _finish_base(profile: bytearray) -> bytes:
    struct.pack_into("<H", profile, 0xFE, melon_crc16(profile[:0xFE]))
    return bytes(profile)


def build_base_profile(ssid: str, primary_dns: str) -> bytes:
    ssid_bytes = ssid.encode("ascii")
    if not 1 <= len(ssid_bytes) <= 32:
        raise ValueError("SSID는 ASCII 1~32바이트여야 합니다.")
    dns = ipaddress.ip_address(primary_dns)
    if dns.version != 4:
        raise ValueError("Nintendo DS DNS는 IPv4여야 합니다.")

    profile = bytearray(PROFILE_SIZE)
    profile[0x40:0x40 + len(ssid_bytes)] = ssid_bytes
    profile[0xC8:0xCC] = dns.packed
    profile[0xE6] = 0x00  # no WEP
    profile[0xE7] = 0x00  # configured/normal
    profile[0xE8] = len(ssid_bytes)
    profile[0xEF] = 0x01  # connection slot exists
    return _finish_base(profile)


def build_unconfigured_profile() -> bytes:
    profile = bytearray(PROFILE_SIZE)
    profile[0xE7] = 0xFF
    profile[0xEF] = 0x01
    return _finish_base(profile)


def build_extended_profile(base: bytes) -> bytes:
    if len(base) != PROFILE_SIZE:
        raise ValueError("base profile size must be 256 bytes")
    profile = bytearray(EXTENDED_PROFILE_SIZE)
    profile[:PROFILE_SIZE] = base
    struct.pack_into("<H", profile, 0x1FE, melon_crc16(profile[0x100:0x1FE]))
    return bytes(profile)


def build_wfc_settings(primary_dns: str, ssid: str = "melonAP") -> bytes:
    configured = build_base_profile(ssid, primary_dns)
    empty = build_unconfigured_profile()
    payload = b"".join(
        [build_extended_profile(configured)]
        + [build_extended_profile(empty)] * 2
        + [configured]
        + [empty] * 2
    )
    if len(payload) != WFC_SETTINGS_SIZE:
        raise AssertionError("unexpected wfcsettings.bin size")
    return payload


def verify_wfc_settings(payload: bytes) -> None:
    if len(payload) != WFC_SETTINGS_SIZE:
        raise ValueError(f"크기가 {len(payload)}바이트입니다. 2304바이트여야 합니다.")
    records = [
        payload[0x000:0x200], payload[0x200:0x400], payload[0x400:0x600],
        payload[0x600:0x700], payload[0x700:0x800], payload[0x800:0x900],
    ]
    for index, record in enumerate(records):
        base = record[:0x100]
        stored = struct.unpack_from("<H", base, 0xFE)[0]
        if stored != melon_crc16(base[:0xFE]):
            raise ValueError(f"프로필 {index + 1} 기본 CRC가 잘못되었습니다.")
        if len(record) == 0x200:
            extended = struct.unpack_from("<H", record, 0x1FE)[0]
            if extended != melon_crc16(record[0x100:0x1FE]):
                raise ValueError(f"프로필 {index + 1} 확장 CRC가 잘못되었습니다.")


def write_profile(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
        print(f"백업: {backup}")
    path.write_bytes(payload)
    verify_wfc_settings(path.read_bytes())
    print(f"적용: {path} ({len(payload)} bytes)")


def main() -> int:
    parser = argparse.ArgumentParser(description="melonDS Nintendo WFC 프로필 생성")
    parser.add_argument("--dns", default="auto", help="사설 서버 IPv4 또는 auto")
    parser.add_argument("--ssid", default="melonAP")
    parser.add_argument(
        "--output", action="append", type=Path,
        help="출력 wfcsettings.bin. 여러 번 지정 가능",
    )
    args = parser.parse_args()
    dns = detect_server_ip("1.1.1.1") if args.dns == "auto" else args.dns
    outputs = args.output or [ROOT / "tools" / "melonDS-1.1" / "wfcsettings.bin"]
    payload = build_wfc_settings(dns, args.ssid)
    for output in outputs:
        write_profile(output.resolve(), payload)
    print(f"SSID={args.ssid} / DHCP=자동 / Primary DNS={dns}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
