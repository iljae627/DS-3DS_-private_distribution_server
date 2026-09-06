from __future__ import annotations

import base64
import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PacketLog:
    def __init__(self, path: Path, capture_raw: bool = True) -> None:
        self.path = path
        self.capture_raw = capture_raw
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, protocol: str, raw: bytes | None = None, **fields: Any) -> None:
        entry: dict[str, Any] = {
            "time": datetime.now(timezone.utc).isoformat(),
            "protocol": protocol,
            **fields,
        }
        if raw is not None:
            entry["raw_length"] = len(raw)
            entry["raw_sha256"] = hashlib.sha256(raw).hexdigest()
            if self.capture_raw:
                entry["raw_base64"] = base64.b64encode(raw).decode("ascii")
        line = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(line + "\n")


def safe_fields(fields: dict[str, str]) -> dict[str, str]:
    """Keep protocol values useful while replacing reusable login tokens."""
    result: dict[str, str] = {}
    for key, value in fields.items():
        if key.lower() in {"token", "userid", "passwd", "password", "auth"}:
            result[key] = f"<sha256:{hashlib.sha256(value.encode()).hexdigest()[:12]};len={len(value)}>"
        else:
            result[key] = value
    return result
