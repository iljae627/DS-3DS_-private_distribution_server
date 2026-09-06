"""Build a Gen 4 DLS1 .myg container from an 856-byte .pcd Wonder Card."""

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DLC_DIR = BASE_DIR / "dlc" / "CPUK"
PCD_FILE = next(BASE_DIR.glob("*.pcd"), None)
TEMPLATE_FILE = DLC_DIR / "17pSecretKey.myg"
OUTPUT_FILE = DLC_DIR / "mew.myg"
MYG_HEADER_SIZE = 80
PCD_SIZE = 856


def main():
    if PCD_FILE is None:
        raise FileNotFoundError("No .pcd source file found beside build_myg.py")

    pcd = PCD_FILE.read_bytes()
    template = TEMPLATE_FILE.read_bytes()
    if len(pcd) != PCD_SIZE:
        raise ValueError(f"Expected a {PCD_SIZE}-byte Gen 4 PCD, got {len(pcd)} bytes")
    if len(template) != MYG_HEADER_SIZE + PCD_SIZE:
        raise ValueError(f"Unexpected template size: {len(template)}")
    if template[MYG_HEADER_SIZE:MYG_HEADER_SIZE + 4] != b"\x01\x00\x00\x00":
        raise ValueError("Template does not contain a Gen 4 PCD payload at offset 0x50")

    OUTPUT_FILE.write_bytes(template[:MYG_HEADER_SIZE] + pcd)
    print(f"[*] Built {OUTPUT_FILE.name}: {OUTPUT_FILE.stat().st_size} bytes")


if __name__ == "__main__":
    main()
