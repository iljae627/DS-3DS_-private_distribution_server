"""Safe Gen 4 PK4 -> template PCD -> MYG builder.

This tool deliberately uses a known-good PCD/MYG pair as metadata/container
templates. It replaces only the encrypted 236-byte PGT Pokémon payload, which
avoids inventing unknown Wonder Card metadata fields.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

PK4_STORED_SIZE = 136
PK4_PARTY_SIZE = 236
PCD_SIZE = 856
PGT_SIZE = 260
PGT_POKEMON_OFFSET = 8
MYG_HEADER_SIZE = 80
MYG_SIZE = MYG_HEADER_SIZE + PCD_SIZE

BLOCK_POSITIONS = (
    (0, 1, 2, 3), (0, 1, 3, 2), (0, 2, 1, 3), (0, 3, 1, 2),
    (0, 2, 3, 1), (0, 3, 2, 1), (1, 0, 2, 3), (1, 0, 3, 2),
    (2, 0, 1, 3), (3, 0, 1, 2), (2, 0, 3, 1), (3, 0, 2, 1),
    (1, 2, 0, 3), (1, 3, 0, 2), (2, 1, 0, 3), (3, 1, 0, 2),
    (2, 3, 0, 1), (3, 2, 0, 1), (1, 2, 3, 0), (1, 3, 2, 0),
    (2, 1, 3, 0), (3, 1, 2, 0), (2, 3, 1, 0), (3, 2, 1, 0),
)
BLOCK_POSITIONS_INVERT = (
    0, 1, 2, 4, 3, 5, 6, 7, 12, 18, 13, 19,
    8, 10, 14, 20, 16, 22, 9, 11, 15, 21, 17, 23,
)


def _crypt_words(data: bytearray, seed: int) -> None:
    """Gen 4 LCRNG XOR stream used for PK4 core and party regions."""
    for offset in range(0, len(data), 2):
        seed = (0x41C64E6D * seed + 0x6073) & 0xFFFFFFFF
        word = struct.unpack_from("<H", data, offset)[0] ^ (seed >> 16)
        struct.pack_into("<H", data, offset, word)


def _shuffle_blocks(data: bytearray, order: tuple[int, int, int, int]) -> bytearray:
    if len(data) != 128:
        raise ValueError("PK4 core must be 128 bytes")
    blocks = [data[index * 32 : (index + 1) * 32] for index in range(4)]
    return bytearray().join(blocks[index] for index in order)


def is_encrypted_pk4(data: bytes) -> bool:
    """Same practical heuristic used by PKHeX for Gen 4/5 entity data."""
    return struct.unpack_from("<I", data, 0x64)[0] != 0


def decrypt_pk4(data: bytes) -> bytearray:
    if len(data) != PK4_PARTY_SIZE:
        raise ValueError("decrypt_pk4 expects a 236-byte party PK4")
    result = bytearray(data)
    pid = struct.unpack_from("<I", result, 0)[0]
    checksum = struct.unpack_from("<H", result, 6)[0]
    core = result[8:PK4_STORED_SIZE]
    _crypt_words(core, checksum)
    result[8:PK4_STORED_SIZE] = _shuffle_blocks(core, BLOCK_POSITIONS[(pid >> 13) & 31])
    party = result[PK4_STORED_SIZE:]
    _crypt_words(party, pid)
    result[PK4_STORED_SIZE:] = party
    return result


def encrypt_pk4(data: bytes) -> bytearray:
    if len(data) != PK4_PARTY_SIZE:
        raise ValueError("encrypt_pk4 expects a 236-byte party PK4")
    result = bytearray(data)
    pid = struct.unpack_from("<I", result, 0)[0]
    checksum = struct.unpack_from("<H", result, 6)[0]
    sv = (pid >> 13) & 31
    core = _shuffle_blocks(result[8:PK4_STORED_SIZE], BLOCK_POSITIONS[BLOCK_POSITIONS_INVERT[sv]])
    _crypt_words(core, checksum)
    result[8:PK4_STORED_SIZE] = core
    party = result[PK4_STORED_SIZE:]
    _crypt_words(party, pid)
    result[PK4_STORED_SIZE:] = party
    return result


def validate_pk4(data: bytes) -> tuple[int, int]:
    """Return (species, checksum); raise on an invalid PK4 checksum."""
    if len(data) not in (PK4_STORED_SIZE, PK4_PARTY_SIZE):
        raise ValueError(f"PK4 must be 136 or 236 bytes, got {len(data)}")
    party = bytearray(data.ljust(PK4_PARTY_SIZE, b"\0"))
    plain = decrypt_pk4(party) if is_encrypted_pk4(party) else party
    expected = struct.unpack_from("<H", plain, 6)[0]
    calculated = sum(struct.unpack_from("<64H", plain, 8)) & 0xFFFF
    if calculated != expected:
        raise ValueError(f"invalid PK4 checksum: stored 0x{expected:04X}, calculated 0x{calculated:04X}")
    return struct.unpack_from("<H", plain, 8)[0], expected


def normalise_encrypted_party_pk4(data: bytes) -> bytes:
    """Validate input then return the encrypted 236-byte representation PGT requires."""
    validate_pk4(data)
    party = bytearray(data.ljust(PK4_PARTY_SIZE, b"\0"))
    plain = decrypt_pk4(party) if is_encrypted_pk4(party) else party
    return bytes(encrypt_pk4(plain))


def build_pcd(pk4_path: Path, template_pcd: Path, output_pcd: Path) -> int:
    pk4 = pk4_path.read_bytes()
    species, _ = validate_pk4(pk4)
    pcd = bytearray(template_pcd.read_bytes())
    if len(pcd) != PCD_SIZE:
        raise ValueError(f"PCD template must be {PCD_SIZE} bytes")
    if pcd[0] != 1:  # GiftType4.Pokemon
        raise ValueError("PCD template is not a Pokémon gift (PGT GiftType must be 1)")
    pcd[PGT_POKEMON_OFFSET : PGT_POKEMON_OFFSET + PK4_PARTY_SIZE] = normalise_encrypted_party_pk4(pk4)
    output_pcd.parent.mkdir(parents=True, exist_ok=True)
    output_pcd.write_bytes(pcd)
    return species


def build_myg(pcd_path: Path, template_myg: Path, output_myg: Path) -> None:
    pcd = pcd_path.read_bytes()
    template = template_myg.read_bytes()
    if len(pcd) != PCD_SIZE:
        raise ValueError(f"PCD input must be {PCD_SIZE} bytes")
    if len(template) != MYG_SIZE:
        raise ValueError(f"MYG template must be {MYG_SIZE} bytes")
    output_myg.parent.mkdir(parents=True, exist_ok=True)
    output_myg.write_bytes(template[:MYG_HEADER_SIZE] + pcd)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Gen 4 PCD and DLS1 MYG from a PKHeX PK4.")
    parser.add_argument("pk4", type=Path, help="136-byte boxed or 236-byte party PK4 exported by PKHeX")
    parser.add_argument("--template-pcd", type=Path, required=True, help="known-good Pokémon PCD used for metadata")
    parser.add_argument("--template-myg", type=Path, required=True, help="known-good 936-byte MYG used for its 80-byte header")
    parser.add_argument("--pcd-out", type=Path, required=True)
    parser.add_argument("--myg-out", type=Path, required=True)
    args = parser.parse_args()

    species = build_pcd(args.pk4, args.template_pcd, args.pcd_out)
    build_myg(args.pcd_out, args.template_myg, args.myg_out)
    print(f"OK: species={species}, PCD={args.pcd_out} ({PCD_SIZE} bytes), MYG={args.myg_out} ({MYG_SIZE} bytes)")


if __name__ == "__main__":
    main()
