import argparse
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

parser = argparse.ArgumentParser(description="Dream World HTTP server")
parser.add_argument("--debug", action="store_true")

args = parser.parse_args()

args.game_sync = False
if (Path(os.environ.get("PDW_SAVE_DIR", ROOT_DIR / "save_data")) / "gscd.txt").exists():
    args.game_sync = True
