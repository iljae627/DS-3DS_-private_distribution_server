"""One-command PKHeX PK4 -> PCD -> MYG conversion using bundled references."""

from pathlib import Path
import argparse

from gen4_gift_builder import build_myg, build_pcd


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "samples" / "reference"
OUTPUT = ROOT / "samples" / "output"


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert one PKHeX Gen 4 PK4 to PCD and MYG.")
    parser.add_argument("pk4", type=Path, help="236-byte party PK4 exported by PKHeX")
    parser.add_argument("--name", help="output basename; defaults to the PK4 filename")
    args = parser.parse_args()

    name = args.name or args.pk4.stem
    pcd_out = OUTPUT / f"{name}.pcd"
    myg_out = OUTPUT / f"{name}.myg"
    species = build_pcd(args.pk4, REFERENCE / "mew_reference.pcd", pcd_out)
    build_myg(pcd_out, REFERENCE / "mew_reference.myg", myg_out)
    print(f"OK: species={species}; created {pcd_out} and {myg_out}")
    print("Deploy manually: copy the MYG into server/dlc/CPUK and set OFFER_FILE in server/http_server.py.")


if __name__ == "__main__":
    main()
