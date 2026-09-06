from __future__ import annotations

import base64
import struct
from pathlib import Path


PK4_BOX_SIZE = 136
PK4_PARTY_SIZE = 236

# The 24 permutations selected by bits 13..17 of the personality value.
_ORDERS = (
    (0, 1, 2, 3), (0, 1, 3, 2), (0, 2, 1, 3), (0, 2, 3, 1),
    (0, 3, 1, 2), (0, 3, 2, 1), (1, 0, 2, 3), (1, 0, 3, 2),
    (2, 0, 1, 3), (2, 0, 3, 1), (3, 0, 1, 2), (3, 0, 2, 1),
    (1, 2, 0, 3), (1, 3, 0, 2), (2, 1, 0, 3), (2, 3, 0, 1),
    (3, 1, 0, 2), (3, 2, 0, 1), (1, 2, 3, 0), (1, 3, 2, 0),
    (2, 1, 3, 0), (2, 3, 1, 0), (3, 1, 2, 0), (3, 2, 1, 0),
)


def _crypt_words(words: list[int], seed: int, start: int, end: int) -> None:
    for index in range(start, end):
        seed = (seed * 0x41C64E6D + 0x6073) & 0xFFFFFFFF
        words[index] ^= seed >> 16


def _reorder_blocks(words: list[int], pid: int, inverse: bool = False) -> list[int]:
    order = _ORDERS[((pid & 0x3E000) >> 13) % 24]
    blocks = [words[i * 16:(i + 1) * 16] for i in range(4)]
    if not inverse:
        return [word for block_id in order for word in blocks[block_id]]

    restored: list[list[int] | None] = [None, None, None, None]
    for wire_position, original_id in enumerate(order):
        restored[original_id] = blocks[wire_position]
    return [word for block in restored for word in (block or [])]


def encrypt_pk4(decrypted: bytes) -> bytes:
    """Encrypt a decrypted 136/236-byte Gen-IV PKM for the game's wire format."""
    if len(decrypted) not in (PK4_BOX_SIZE, PK4_PARTY_SIZE):
        raise ValueError("PK4 must be 136 (box) or 236 (party) bytes")
    pid, sanity, checksum = struct.unpack_from("<IHH", decrypted)
    body = list(struct.unpack_from(f"<{(len(decrypted) - 8) // 2}H", decrypted, 8))
    body = _reorder_blocks(body[:64], pid) + body[64:]
    words = [pid, sanity, checksum, *body]
    _crypt_words(words, checksum, 3, 67)
    if len(words) > 67:
        _crypt_words(words, pid, 67, len(words))
    return struct.pack("<IHH", words[0], words[1], words[2]) + struct.pack(
        f"<{len(words) - 3}H", *words[3:]
    )


def decrypt_pk4(encrypted: bytes) -> bytes:
    if len(encrypted) not in (PK4_BOX_SIZE, PK4_PARTY_SIZE):
        raise ValueError("encrypted PK4 must be 136 or 236 bytes")
    pid, sanity, checksum = struct.unpack_from("<IHH", encrypted)
    body = list(struct.unpack_from(f"<{(len(encrypted) - 8) // 2}H", encrypted, 8))
    words = [pid, sanity, checksum, *body]
    _crypt_words(words, checksum, 3, 67)
    if len(words) > 67:
        _crypt_words(words, pid, 67, len(words))
    restored = _reorder_blocks(words[3:67], pid, inverse=True) + words[67:]
    return struct.pack("<IHH", pid, sanity, checksum) + struct.pack(
        f"<{len(restored)}H", *restored
    )


def add_minimal_party_tail(box_data: bytes, level: int) -> bytes:
    """Make a wire-sized party PK4 when only a box-sized export is available.

    The game normally recalculates party stats after receiving/depositing it. A true
    236-byte party export from PKHeX is still preferred.
    """
    if len(box_data) != PK4_BOX_SIZE:
        raise ValueError("expected a 136-byte boxed PK4")
    if not 1 <= level <= 100:
        raise ValueError("level must be 1..100")
    tail = bytearray(100)
    tail[4] = level  # absolute 0x8C
    tail[25] = 0x02
    tail[26] = 0x07
    tail[27:50] = b"\xFF" * 23
    tail[52:54] = b"\xFF\xFF"
    tail[56:63] = b"\xFF" * 7
    tail[63:65] = b"\x88\x01"
    tail[65:70] = b"\xFF" * 5
    tail[70:72] = b"\xAC\x01"
    tail[72:76] = b"\xFF" * 4
    tail[99] = 0x07
    return box_data + bytes(tail)


def pk4_metadata(data: bytes, fallback_level: int = 50) -> dict[str, int | str | bool]:
    if len(data) not in (PK4_BOX_SIZE, PK4_PARTY_SIZE):
        raise ValueError("PK4 must be 136 or 236 bytes")
    species = int.from_bytes(data[0x08:0x0A], "little")
    pid = int.from_bytes(data[0:4], "little")
    gender_bits = data[0x40] & 0x06
    gender = "genderless" if gender_bits & 4 else ("female" if gender_bits & 2 else "male")
    level = data[0x8C] if len(data) == PK4_PARTY_SIZE and data[0x8C] else fallback_level
    return {
        "species": species,
        "pid": pid,
        "gender": gender,
        "level": level,
        "party_size": len(data) == PK4_PARTY_SIZE,
    }


def build_gts_result_packet(decrypted: bytes, fallback_level: int = 50) -> bytes:
    if len(decrypted) == PK4_BOX_SIZE:
        decrypted = add_minimal_party_tail(decrypted, fallback_level)
    if len(decrypted) != PK4_PARTY_SIZE:
        raise ValueError("GTS distribution requires a 136/236-byte Gen-IV PKM")
    meta = pk4_metadata(decrypted, fallback_level)
    packet = bytearray(encrypt_pk4(decrypted))
    packet += decrypted[0x08:0x0A]  # species
    packet += b"\x03" if decrypted[0x40] & 0x04 else bytes([((decrypted[0x40] & 2) + 1)])
    packet += bytes([int(meta["level"])])
    packet += b"\x01\x00\x03\x00\x00\x00\x00\x00"  # harmless trade request
    packet += b"\x00" * 20
    packet += decrypted[0x68:0x78]  # OT name
    packet += decrypted[0x0C:0x0E]  # public trainer ID
    packet += b"\xDB\x02"          # country/city compatibility fields
    packet += b"\x46\x00\x07\x02"  # sprite/status/version/language
    return bytes(packet)


def decode_gts_upload(encoded: str) -> bytes:
    """Decode the URL-safe, stream-ciphered `data` field from GTS post.asp."""
    raw = base64.b64decode(encoded.replace("-", "+").replace("_", "/") + "===")
    if len(raw) < 244:
        raise ValueError("GTS upload is shorter than the expected 244-byte wrapper")
    key = int.from_bytes(raw[:4], "big") ^ 0x4A3B2C1D
    state = key | (key << 16)
    clear = bytearray()
    for value in raw[4:244]:
        state = (state * 0x45 + 0x1111) & 0x7FFFFFFF
        clear.append(value ^ ((state >> 16) & 0xFF))
    return decrypt_pk4(bytes(clear[4:]))


def load_pk4(path: Path, fallback_level: int = 50) -> bytes:
    data = path.read_bytes()
    if len(data) == PK4_BOX_SIZE:
        return add_minimal_party_tail(data, fallback_level)
    if len(data) != PK4_PARTY_SIZE:
        raise ValueError(f"{path.name}: expected 136 or 236 bytes, got {len(data)}")
    return data
