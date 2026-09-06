from __future__ import annotations

import argparse
import base64
import json
import socket
import struct
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def dns_query(name: str) -> bytes:
    labels = b"".join(bytes((len(part),)) + part.encode("ascii") for part in name.split(".")) + b"\0"
    return b"\x53\x44\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + labels + struct.pack("!HH", 1, 1)


def request(url: str, body: bytes | None = None, content_type: str | None = None) -> bytes:
    headers = {"Content-Type": content_type} if content_type else {}
    req = urllib.request.Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=5) as response:
        return response.read()


def upload(base: str, kind: str, path: Path, **extra: object) -> dict:
    payload = {
        "kind": kind,
        "file_name": path.name,
        "data_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
        **extra,
    }
    return json.loads(request(
        base + "/admin/upload", json.dumps(payload).encode("utf-8"), "application/json",
    ))


def encoded(value: str) -> str:
    return base64.b64encode(value.encode("ascii")).decode("ascii").replace("=", "*")


def dls(base: str, action: str, contents: str = "") -> bytes:
    values = {"action": encoded(action), "gamecd": encoded("CPUK")}
    if contents:
        values["contents"] = encoded(contents)
    return request(base + "/download", urllib.parse.urlencode(values).encode("ascii"), "application/x-www-form-urlencoded")


def main() -> int:
    parser = argparse.ArgumentParser(description="실행 중인 DS 배포 서버 종합 점검")
    parser.add_argument("--server-ip", required=True)
    args = parser.parse_args()
    server_ip = str(args.server_ip)
    base = "http://127.0.0.1"

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(3)
        sock.sendto(dns_query("gamestats2.gs.nintendowifi.net"), (server_ip, 53))
        answer = sock.recv(4096)
    expected = socket.inet_aton(server_ip)
    if answer[-4:] != expected:
        raise RuntimeError(f"DNS 응답 불일치: {socket.inet_ntoa(answer[-4:])}")

    admin = request(base + "/")
    if b"DS Pok" not in admin:
        raise RuntimeError("관리 화면 응답이 올바르지 않습니다.")

    pokemon = ROOT / "samples" / "input" / "0129 - 잉어킹 - 34FB564BC3B0.pk4"
    gift = ROOT / "samples" / "output" / "ARC_v2.pcd"
    if not upload(base, "pokemon", pokemon, level=50).get("ok"):
        raise RuntimeError("PK4 활성화 실패")
    if not upload(base, "gen4", gift).get("ok"):
        raise RuntimeError("PCD 활성화 실패")

    token = request(base + "/pokemondpds/worldexchange/info.asp?pid=1")
    info = request(base + "/pokemondpds/worldexchange/info.asp?pid=1&hash=1")
    result = request(base + "/pokemondpds/worldexchange/result.asp?pid=1&hash=1")
    if len(token) != 32 or info != b"\x01\x00" or len(result) <= 236:
        raise RuntimeError("GTS 흐름 응답이 올바르지 않습니다.")

    count = dls(base, "count")
    listing = dls(base, "list")
    contents = dls(base, "contents", "card.myg")
    if count != b"1" or b".myg" not in listing or len(contents) != 936:
        raise RuntimeError("4세대 DLS 흐름 응답이 올바르지 않습니다.")

    report = {
        "dns": socket.inet_ntoa(answer[-4:]),
        "admin_bytes": len(admin),
        "gts_token_bytes": len(token),
        "gts_result_bytes": len(result),
        "dls_count": count.decode("ascii"),
        "dls_list": listing.decode("ascii", errors="replace").strip(),
        "dls_contents_bytes": len(contents),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
