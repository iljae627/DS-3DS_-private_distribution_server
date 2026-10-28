#!/usr/bin/env python3
"""Windows Generation V server using the Generation IV network transport."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import server  # Register the Generation V implementation for the shared transport.

_path = Path(__file__).resolve().parent.parent / "4세대-배포" / "windows_server.py"
_spec = importlib.util.spec_from_file_location("gen5_windows_transport", _path)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"공통 Windows 전송 모듈을 불러올 수 없습니다: {_path}")
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

if __name__ == "__main__":
    raise SystemExit(_module.main())

