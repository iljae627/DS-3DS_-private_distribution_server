#!/usr/bin/env python3
"""Run the Game Sync and Dream World servers in the correct order."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
GSCD_FILE = ROOT / "save_data" / "gscd.txt"


def has_game_sync_id() -> bool:
    return GSCD_FILE.is_file() and bool(GSCD_FILE.read_text(encoding="utf-8").strip())


def start(command: list[str], cwd: Path) -> subprocess.Popen:
    return subprocess.Popen(command, cwd=cwd)


def stop(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dream World all-in-one launcher")
    parser.add_argument("--game-sync-only", action="store_true")
    parser.add_argument("--web-only", action="store_true")
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.game_sync_only and args.web_only:
        raise SystemExit("--game-sync-only and --web-only cannot be used together")

    game_sync = None
    web = None
    try:
        if not args.web_only:
            print("[1/2] Starting Game Sync/DNS server...", flush=True)
            game_sync = start([sys.executable, "server.py"], ROOT / "game_sync_server")

        if not args.game_sync_only:
            if not has_game_sync_id():
                if args.web_only:
                    print("No Game Sync ID was found. Tuck in a Pokemon first.", file=sys.stderr)
                    return 2
                print("[wait] On the game, create a Game Sync ID and tuck in a Pokemon.", flush=True)
                print("       The web server will start automatically afterwards.", flush=True)

            while not has_game_sync_id():
                if game_sync is not None and game_sync.poll() is not None:
                    return game_sync.returncode or 1
                time.sleep(1)

            print("[2/2] Starting Dream World web server at http://127.0.0.1:8080/", flush=True)
            command = [sys.executable, "main.py"]
            if args.debug:
                command.append("--debug")
            web = start(command, ROOT)

        watched = [p for p in (game_sync, web) if p is not None]
        while watched:
            for process in watched:
                code = process.poll()
                if code is not None:
                    return code
            time.sleep(0.5)
        return 0
    except KeyboardInterrupt:
        print("\nStopping Dream World servers...", flush=True)
        return 0
    finally:
        stop(web)
        stop(game_sync)


if __name__ == "__main__":
    raise SystemExit(main())
