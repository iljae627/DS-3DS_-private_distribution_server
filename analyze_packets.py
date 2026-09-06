from __future__ import annotations

import argparse
import base64
import collections
import json
import shutil
import subprocess
import sys
from pathlib import Path

from ds_server.gift_converter import gift_metadata
from ds_server.pokemon import pk4_metadata


ROOT = Path(__file__).resolve().parent


def load_entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            print(f"무시: {path}:{number}: {exc}", file=sys.stderr)
    return entries


def hexdump(data: bytes, width: int = 16) -> str:
    rows = []
    for offset in range(0, len(data), width):
        part = data[offset:offset + width]
        hexes = " ".join(f"{value:02x}" for value in part)
        ascii_text = "".join(chr(value) if 32 <= value < 127 else "." for value in part)
        rows.append(f"{offset:08x}  {hexes:<{width * 3 - 1}}  |{ascii_text}|")
    return "\n".join(rows)


def summarize(entries: list[dict]) -> None:
    print(f"총 이벤트: {len(entries)}")
    counts = collections.Counter(entry.get("protocol", "unknown") for entry in entries)
    for protocol, count in counts.most_common():
        print(f"  {protocol:18} {count:6}")
    domains = collections.Counter(
        entry.get("domain") for entry in entries if entry.get("protocol") == "dns"
    )
    if domains:
        print("\nDNS 상위 도메인:")
        for domain, count in domains.most_common(15):
            print(f"  {count:5}  {domain}")
    paths = collections.Counter(
        (entry.get("method"), entry.get("path"))
        for entry in entries if entry.get("protocol") == "http"
    )
    if paths:
        print("\nHTTP 경로:")
        for (method, path), count in paths.most_common(20):
            print(f"  {count:5}  {method} {path}")
    actions = collections.Counter(
        (entry.get("generation"), entry.get("action"))
        for entry in entries if entry.get("protocol") == "dls"
    )
    if actions:
        print("\nDLS 흐름:")
        for (generation, action), count in actions.items():
            print(f"  {count:5}  Gen {generation} {action}")


def inspect_file(path: Path) -> None:
    data = path.read_bytes()
    print(f"파일: {path}\n크기: {len(data)} bytes\nSHA-256: ", end="")
    import hashlib
    print(hashlib.sha256(data).hexdigest())
    try:
        print("형식:", json.dumps(gift_metadata(data), ensure_ascii=False))
        return
    except ValueError:
        pass
    try:
        print("형식:", json.dumps(pk4_metadata(data), ensure_ascii=False))
        return
    except ValueError:
        pass
    print("형식: 알 수 없음")


def analyze_pcap(path: Path) -> int:
    tshark = shutil.which("tshark")
    if not tshark:
        print("tshark가 없습니다. Wireshark를 설치하거나 JSONL 애플리케이션 로그를 분석하세요.", file=sys.stderr)
        return 2
    command = [
        tshark, "-r", str(path), "-Y", "dns || http",
        "-T", "fields", "-E", "separator=|", "-E", "header=y",
        "-e", "frame.number", "-e", "ip.src", "-e", "ip.dst",
        "-e", "dns.qry.name", "-e", "http.request.method", "-e", "http.request.uri",
    ]
    return subprocess.run(command, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="DS 서버 패킷/배포 파일 분석기")
    parser.add_argument("--log", type=Path, default=ROOT / "logs" / "packets.jsonl")
    parser.add_argument("--tail", type=int, default=0, help="마지막 N개 이벤트를 JSON으로 표시")
    parser.add_argument("--entry", type=int, help="0부터 시작하는 이벤트 번호 상세/hex 표시")
    parser.add_argument("--file", type=Path, help="PK4/PCD/PGF/MYG/BIN 파일 구조 식별")
    parser.add_argument("--pcap", type=Path, help="tshark로 pcap/pcapng의 DNS·HTTP를 표시")
    args = parser.parse_args()
    if args.file:
        inspect_file(args.file)
        return 0
    if args.pcap:
        return analyze_pcap(args.pcap)
    entries = load_entries(args.log)
    summarize(entries)
    if args.tail:
        print("\n최근 이벤트:")
        for index, entry in list(enumerate(entries))[-args.tail:]:
            print(f"[{index}] {json.dumps(entry, ensure_ascii=False, indent=2)}")
    if args.entry is not None:
        entry = entries[args.entry]
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        if entry.get("raw_base64"):
            print("\nRaw bytes:\n" + hexdump(base64.b64decode(entry["raw_base64"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
