from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any


DEFAULT_STATE: dict[str, Any] = {
    "pokemon": None,
    "gen4_gift": None,
    "gen5_gift": None,
}


class ServerState:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.data_dir = root / "data"
        self.upload_dir = self.data_dir / "uploads"
        self.received_dir = self.data_dir / "received"
        self.path = self.data_dir / "state.json"
        self._lock = threading.RLock()
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.received_dir.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return dict(DEFAULT_STATE)
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            return {**DEFAULT_STATE, **loaded}
        except (OSError, json.JSONDecodeError):
            return dict(DEFAULT_STATE)

    def _save(self) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._state))

    def set_item(self, slot: str, value: dict[str, Any] | None) -> None:
        if slot not in DEFAULT_STATE:
            raise KeyError(slot)
        with self._lock:
            self._state[slot] = value
            self._save()

    def get_item(self, slot: str) -> dict[str, Any] | None:
        with self._lock:
            value = self._state.get(slot)
            return dict(value) if value else None

    def file_for(self, slot: str) -> Path | None:
        item = self.get_item(slot)
        if not item:
            return None
        path = (self.root / item["path"]).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("state file points outside the project")
        return path if path.is_file() else None
