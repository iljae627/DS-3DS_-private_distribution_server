"""Self-test for the Gen 4 template builder using the bundled Arceus sample."""

import importlib.util
from pathlib import Path
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gen4_gift_builder", Path(__file__).with_name("gen4_gift_builder.py"))
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def main():
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        pcd_out = directory / "arc.pcd"
        myg_out = directory / "arc.myg"
        species = builder.build_pcd(
            ROOT / "samples" / "input" / "ARC.pk4",
            ROOT / "samples" / "reference" / "mew_reference.pcd",
            pcd_out,
        )
        builder.build_myg(pcd_out, ROOT / "samples" / "reference" / "mew_reference.myg", myg_out)
        assert species == 493
        assert pcd_out.stat().st_size == builder.PCD_SIZE
        assert myg_out.stat().st_size == builder.MYG_SIZE
        embedded = pcd_out.read_bytes()[8 : 8 + builder.PK4_PARTY_SIZE]
        assert builder.validate_pk4(embedded)[0] == 493
    print("OK: PK4 -> PCD -> MYG structural round-trip passed")


if __name__ == "__main__":
    main()
