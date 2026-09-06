from __future__ import annotations

import struct

from .pokemon import encrypt_pk4


GEN4_PCD_SIZE = 856
GEN4_DLS_SIZE = 936
GEN5_PGF_SIZE = 204
GEN5_DLS_SIZE = 720

LANGUAGE_IDS = {"j": 1, "e": 2, "f": 3, "i": 4, "g": 5, "s": 7, "k": 8}
VERSION_BITS = {"w": 0x00100000, "b": 0x00200000, "w2": 0x00400000, "b2": 0x00800000}


def crc16_ccitt(data: bytes, initial: int = 0xFFFF) -> int:
    crc = initial
    for value in data:
        for mask in (0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01):
            bit = bool(crc & 0x8000) ^ bool(value & mask)
            crc = (crc << 1) & 0xFFFF
            if bit:
                crc ^= 0x1021
    return crc


def gen4_pcd_to_dls(data: bytes) -> bytes:
    if len(data) == GEN4_DLS_SIZE:
        return data
    if len(data) != GEN4_PCD_SIZE:
        raise ValueError(f"Gen-IV gift must be 856-byte PCD or 936-byte MYG, got {len(data)}")

    pcd = bytearray(data)
    pokemon = bytes(pcd[0x08:0xF4])
    # Pokémon gifts store a decrypted party PK4 inside preserved PCD files.
    if int.from_bytes(pokemon[0x08:0x0A], "little") != 0:
        pcd[0x08:0xF4] = encrypt_pk4(pokemon)
    return bytes(pcd[0x104:0x154] + pcd)


def version_mask(versions: str) -> int:
    compact = versions.lower().replace(" ", "").replace(",", "")
    selected = 0
    for key in ("w2", "b2"):
        if key in compact:
            selected |= VERSION_BITS[key]
            compact = compact.replace(key, "")
    if "w" in compact:
        selected |= VERSION_BITS["w"]
    if "b" in compact:
        selected |= VERSION_BITS["b"]
    if not selected:
        raise ValueError("versions must contain at least one of: w, b, w2, b2")
    return selected


def gen5_pgf_to_dls(
    data: bytes,
    description: str = "Private distribution",
    language: str = "e",
    versions: str = "wbw2b2",
) -> bytes:
    if len(data) == GEN5_DLS_SIZE:
        expected = int.from_bytes(data[-2:], "little")
        actual = crc16_ccitt(data[:-2])
        if expected != actual:
            raise ValueError(f"720-byte Gen-V gift has an invalid CRC: {expected:04X} != {actual:04X}")
        return data
    if len(data) != GEN5_PGF_SIZE:
        raise ValueError(f"Gen-V gift must be 204-byte PGF or 720-byte BIN, got {len(data)}")
    if language.lower() not in LANGUAGE_IDS:
        raise ValueError("language must be one of e/f/i/g/s/j/k")

    pgf = bytearray(data)
    pgf[0xAC:0xB0] = b"\x00" * 4  # received date must be blank in distribution form
    result = bytearray(pgf)
    result += struct.pack("<I", version_mask(versions))

    normalized = description.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\uFFFE")
    encoded = normalized.encode("utf-16le")
    max_length = 0x2CA - 0xD0 - 2
    result += encoded[:max_length - (max_length % 2)]
    result += b"\xFF\xFF"
    result += b"\xFF" * (0x2CA - len(result))
    result += bytes((0, LANGUAGE_IDS[language.lower()], 0, 0))
    result += struct.pack("<H", crc16_ccitt(result))
    if len(result) != GEN5_DLS_SIZE:
        raise AssertionError(f"internal conversion error: expected 720 bytes, made {len(result)}")
    return bytes(result)


def gift_metadata(data: bytes) -> dict[str, int | str | bool]:
    if len(data) in (GEN4_PCD_SIZE, GEN4_DLS_SIZE):
        pcd = data[-GEN4_PCD_SIZE:]
        return {
            "generation": 4,
            "card_id": int.from_bytes(pcd[0x150:0x152], "little"),
            "size": len(data),
            "wire_ready": len(data) == GEN4_DLS_SIZE,
        }
    if len(data) in (GEN5_PGF_SIZE, GEN5_DLS_SIZE):
        return {
            "generation": 5,
            "card_id": int.from_bytes(data[0xB0:0xB2], "little"),
            "species": int.from_bytes(data[0x1A:0x1C], "little"),
            "size": len(data),
            "wire_ready": len(data) == GEN5_DLS_SIZE,
        }
    raise ValueError(f"unknown gift format/size: {len(data)} bytes")
