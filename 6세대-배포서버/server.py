#!/usr/bin/env python3
"""Pokemon Generation VI Korean private BOSS distribution server."""
from __future__ import annotations
import argparse, base64, hashlib, importlib.util, json, logging, random, re, ssl, subprocess, sys, threading, time
from email.utils import formatdate
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
WC6_SIZE, WC6FULL_SIZE, KOREAN_LANGUAGE = 0x108, 0x310, 8
TASK_ID = "FGONLYT"
KOREAN_BOSS_ATTR = "MYS_KO_K"
LOCAL_HOSTS = {
    "conntest.nintendowifi.net",
    "nppl.c.app.nintendowifi.net",
    "npfl.c.app.nintendowifi.net",
    "npdl.cdn.nintendowifi.net",
    "3ds-fushigi.pokemon-gl.com",
}
LOGGER = logging.getLogger("gen6-distribution")
CONNTEST_BODY = (b'<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" '
                 b'"http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">\r\n'
                 b'<html>\r\n<head>\r\n\t<title>HTML Page</title>\r\n</head>\r\n'
                 b'<body bgcolor="#FFFFFF">\r\nThis is test.html page\r\n</body>\r\n</html>\r\n')

def make_policylist() -> bytes:
    """Return the version-3 3DS BOSS policy list expected after conntest."""
    updated = time.strftime("%Y-%m-%dT%H:%M:%S+0000", time.gmtime())
    priorities = (
        ("0004003000008f02", "basho0"),
        ("000400300000bc00", "OlvNotf"),
        ("000400300000bd00", "OlvNotf"),
        ("000400300000be00", "OlvNotf"),
        ("0004003000008f02", "pl"),
        ("0004013000003400", "sprelay"),
    )
    priority_xml = "".join(
        f"  <Priority>\n    <TitleId>{title}</TitleId>\n    <TaskId>{task}</TaskId>\n"
        f"    <Level>HIGH</Level>\n    <Persistent>true</Persistent>\n"
        f"    <Revive>true</Revive>\n  </Priority>\n"
        for title, task in priorities
    )
    # This mirrors the complete 3DS policy object emitted by Pretendo BOSS.
    return (f'<PolicyList>\n  <MajorVersion>3</MajorVersion>\n'
            f'  <MinorVersion>0</MinorVersion>\n  <ListId>1891</ListId>\n'
            f'  <DefaultStop>false</DefaultStop>\n  <ForceVersionUp>false</ForceVersionUp>\n'
            f'  <UpdateTime>{updated}</UpdateTime>\n{priority_xml}</PolicyList>').encode("utf-8")
GAME_PROFILES = {
    "h0VRqB2YEgq39zvO": ("Pokemon X", 0x0004000000055D00, 0x01),
    "Slv7vHlUOfqrKMpz": ("Pokemon Y", 0x0004000000055E00, 0x02),
    "cRFY0WFHNjPh44If": ("Pokemon Omega Ruby", 0x000400000011C400, 0x08),
    "guBwm9TlQvYvncKn": ("Pokemon Alpha Sapphire", 0x000400000011C500, 0x04),
}

_path = ROOT.parent / "4세대-배포" / "server.py"
_spec = importlib.util.spec_from_file_location("gen6_dns_transport", _path)
if _spec is None or _spec.loader is None: raise RuntimeError(f"DNS 공통 모듈을 읽을 수 없습니다: {_path}")
_DNS = importlib.util.module_from_spec(_spec); sys.modules[_spec.name] = _DNS; _spec.loader.exec_module(_DNS)

@dataclass(frozen=True)
class Gift:
    path: Path; data: bytes; card_id: int; title: str
    full_data: bytes | None = None; boss_data: bytes | None = None
    @property
    def wire_name(self) -> str:
        # Pokemon's production NPFL names use a four-digit card ID followed by
        # an ASCII event identifier (for example 0114_expo_riza).
        if self.card_id == 1022 and self.boss_data is not None:
            return "1022_DubblePack_Kizugusuri_KO"
        if self.card_id == 1004 and hashlib.sha256(self.data).hexdigest() == "d601699946a921b9138cc702623aadf84eea26818c652e04a666381e7c3f1f2f":
            return "1004_OllehTV_Charizard_KO_K"
        if self.card_id == 1064:
            return "1064_XYZ_Zygarde_KO_K"
        if self.card_id == 1503:
            return "1503_Fancy_Vivillon_KO_K"
        if self.card_id == 1504 and hashlib.sha256(self.data).hexdigest() == "18c10bddc7543a3e86554e09757afefa643470ec15238dea08dafa9f4078d6d4":
            return "1504_Steven_Shiny_Beldum_KO_K"
        return f"{self.card_id:04d}_PrivateGift_KO_K"

def _utf16_text(data: bytes, start: int, length: int) -> str:
    raw = data[start:start + length]
    end = next((i for i in range(0, len(raw)-1, 2) if raw[i:i+2] == b"\0\0"), len(raw))
    return raw[:end].decode("utf-16le", "replace").strip()

def load_gifts(directory: Path) -> list[Gift]:
    if not directory.is_dir(): raise FileNotFoundError(f"배포파일 폴더가 없습니다: {directory}")
    gifts = []
    for path in sorted(directory.glob("*.wc6"), key=lambda p: p.name.casefold()):
        data = path.read_bytes()
        if len(data) != WC6_SIZE: raise ValueError(f"{path.name}: WC6는 {WC6_SIZE}바이트여야 합니다 (현재 {len(data)})")
        full_path = path.with_suffix(".wc6full")
        full_data = full_path.read_bytes() if full_path.is_file() else None
        if full_data is not None:
            if len(full_data) != WC6FULL_SIZE:
                raise ValueError(f"{full_path.name}: WC6Full은 {WC6FULL_SIZE}바이트여야 합니다 (현재 {len(full_data)})")
            if full_data[0x208:] != data:
                raise ValueError(f"{full_path.name}: 짝이 되는 WC6 내용과 일치하지 않습니다")
        boss_path = path.with_suffix(".boss")
        boss_data = boss_path.read_bytes() if boss_path.is_file() else None
        if boss_data is not None:
            if len(boss_data) < 0x296 or boss_data[:4] != b"boss":
                raise ValueError(f"{boss_path.name}: 유효한 BOSS 컨테이너가 아닙니다")
            if full_data is None:
                raise ValueError(f"{boss_path.name}: 원본 BOSS와 짝이 되는 WC6Full이 필요합니다")
        gifts.append(Gift(path, data, int.from_bytes(data[:2], "little"),
                          _utf16_text(data, 2, 0x48), full_data, boss_data))
    if not gifts: raise FileNotFoundError(f".wc6 파일이 없습니다: {directory}")
    return gifts

def crc16_ccitt(data: bytes) -> int:
    import binascii
    return binascii.crc_hqx(data, 0xFFFF)

def make_wc6full(gift: Gift, game_mask: int, message: str | None = None) -> bytes:
    if gift.full_data is not None:
        return gift.full_data
    full = bytearray(WC6FULL_SIZE); full[0] = game_mask
    text = (message or gift.title or gift.path.stem).encode("utf-16le") + b"\0\0"
    full[4:4 + min(len(text), 0x1FA)] = text[:0x1FA]
    full[0x1FF] = KOREAN_LANGUAGE; full[0x201] = gift.card_id & 0xFF; full[0x204] = 1
    full[0x205:0x208] = b"FFF"; full[0x208:] = gift.data
    full[0x202:0x204] = b"\0\0"; full[0x202:0x204] = crc16_ccitt(full).to_bytes(2, "little")
    return bytes(full)

def load_boss_key(path: Path) -> bytes:
    if not path.is_file(): raise FileNotFoundError(f"키 파일이 없습니다: {path}\nSD:/gm9/aes_keys.txt를 이 위치로 복사하세요.")
    match = re.search(r"(?im)^\s*slot0x38KeyN\s*=\s*([0-9a-f]{32})\s*$", path.read_text(encoding="utf-8", errors="ignore"))
    if not match: raise ValueError("aes_keys.txt에 유효한 slot0x38KeyN 항목이 없습니다")
    return bytes.fromhex(match.group(1))

def build_boss(key: bytes, profile: tuple[str, int, int], payload: bytes, serial: int) -> bytes:
    req = {"key": key.hex(), "serial": str(serial), "titleId": str(profile[1]),
           "nsDataId": int.from_bytes(payload[0x208:0x20A], "little"),
           "content": base64.b64encode(payload).decode()}
    done = subprocess.run(["node", str(ROOT / "boss_builder.mjs")], input=json.dumps(req), text=True,
                          capture_output=True, check=False, cwd=ROOT)
    if done.returncode: raise RuntimeError(f"BOSS 생성 실패: {done.stderr.strip()}")
    return base64.b64decode(done.stdout.strip(), validate=True)

class GiftState:
    def __init__(self, gifts: list[Gift], key: bytes, selected: int | None):
        self.gifts, self.key, self.fixed = tuple(gifts), key, selected
        self._random, self._selected, self._cache = random.SystemRandom(), {}, {}
        self._lock = threading.RLock()
    def choose(self, client: str, app_id: str) -> Gift:
        gift = self.gifts[self.fixed] if self.fixed is not None else self._random.choice(self.gifts)
        with self._lock: self._selected[(client, app_id)] = gift
        return gift
    def current(self, client: str, app_id: str) -> Gift:
        with self._lock: gift = self._selected.get((client, app_id))
        return gift or self.choose(client, app_id)
    def boss(self, app_id: str, gift: Gift) -> bytes:
        if gift.boss_data is not None:
            return gift.boss_data
        profile, stamp = GAME_PROFILES[app_id], gift.path.stat().st_mtime_ns
        ck = (app_id, gift.path, stamp)
        with self._lock:
            if ck not in self._cache:
                self._cache[ck] = build_boss(self.key, profile, make_wc6full(gift, profile[2]), stamp & 0xFFFFFFFFFFFFFFFF)
            return self._cache[ck]

def make_filelist(gift: Gift) -> bytes:
    # Production Pokemon MYS rows use Attribute 2=F and Attribute 3=N.
    # Attribute 2 is not present in the request filter, but the game still
    # checks it when deciding whether an NPFL entry is a downloadable gift.
    row = f"{gift.wire_name}\t\t{KOREAN_BOSS_ATTR}\tF\tN\t{WC6FULL_SIZE}\t{int(time.time())}\r\n".encode()
    size = 0
    while True:
        tail = f"{size:>10}\r\n".encode() + row; updated = 42 + len(tail)
        if updated == size: break
        size = updated
    return hashlib.sha1(tail).hexdigest().encode() + b"\r\n" + tail

class Handler(BaseHTTPRequestHandler):
    server_version, protocol_version = "nginx", "HTTP/1.1"
    def log_message(self, fmt: str, *args: object) -> None: LOGGER.info("HTTPS %s %s", self.client_address[0], fmt % args)
    def do_GET(self) -> None:
        path = unquote(urlsplit(self.path).path); parts = path.strip("/").split("/")
        host = self.headers.get("Host", "").split(":", 1)[0].lower()
        if host == "conntest.nintendowifi.net":
            return self._conntest()
        if host == "nppl.c.app.nintendowifi.net" and len(parts) >= 4 and parts[:3] == ["p01", "policylist", "3"]:
            return self._policylist(parts[3])
        if len(parts) >= 4 and parts[:2] == ["p01", "filelist"]: return self._filelist(parts[2], parts[3])
        if len(parts) >= 5 and parts[:2] == ["p01", "nsa"]: return self._download(parts[2], parts[3], parts[-1])
        if path == "/health": return self._reply(200, b"ok\n", "text/plain")
        self._reply(404, b"not found\n", "text/plain")
    def _conntest(self) -> None:
        # The 3DS checks X-Organization and the historical test page, not only status 200.
        body = CONNTEST_BODY
        response = (b"HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n"
                    b"X-Organization: Nintendo\r\nServer: BigIP\r\nConnection: close\r\n"
                    + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
        self.wfile.write(response); self.close_connection = True
        LOGGER.info("connection-test client=%s status=200 bytes=%d", self.client_address[0], len(body))
    def _policylist(self, country_code: str) -> None:
        body = make_policylist()
        LOGGER.info("NPPL policy client=%s country=%s bytes=%d", self.client_address[0], country_code, len(body))
        self._reply(200, body, "application/xml; charset=utf-8")
    def _filelist(self, app_id: str, task: str) -> None:
        if app_id not in GAME_PROFILES or task != TASK_ID: return self._reply(403, b"forbidden\n", "text/plain")
        gift = self.server.state.choose(self.client_address[0], app_id)
        body = make_filelist(gift)
        LOGGER.info("선택 client=%s game=%s gift=%s npfl_name=%s attr1=%s attr2=F attr3=N bytes=%d",
                    self.client_address[0], GAME_PROFILES[app_id][0], gift.path.name,
                    gift.wire_name, KOREAN_BOSS_ATTR, len(body))
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Last-Modified", formatdate(time.time() - 5, usegmt=True))
        self.send_header("Cache-Control", "private, must-revalidate, max-age=0")
        self.end_headers()
        self.wfile.write(body)
    def _download(self, app_id: str, task: str, filename: str) -> None:
        if app_id not in GAME_PROFILES or task != TASK_ID: return self._reply(404, b"not found\n", "text/plain")
        gift = self.server.state.current(self.client_address[0], app_id)
        if filename != gift.wire_name: return self._reply(404, b"not found\n", "text/plain")
        try: body = self.server.state.boss(app_id, gift)
        except Exception as exc:
            LOGGER.exception("BOSS 생성 오류: %s", exc); return self._reply(500, b"BOSS build failed\n", "text/plain")
        self._reply(200, body, "application/octet-stream", True)
    def _reply(self, status: int, body: bytes, content_type: str, attachment: bool = False) -> None:
        self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, max-age=0")
        if attachment: self.send_header("Content-Disposition", "attachment"); self.send_header("Content-Transfer-Encoding", "binary")
        self.end_headers(); self.wfile.write(body)

def select_gift(gifts: list[Gift], value: str) -> int | None:
    if value.lower() == "random": return None
    if value.lower() == "ask":
        print("\n배포할 WC6를 선택하세요 (0 = 요청마다 무작위)")
        for i, g in enumerate(gifts, 1): print(f" {i}. #{g.card_id:04d} {g.title or g.path.stem}")
        value = input("번호: ").strip() or "0"
    number = int(value)
    if number == 0: return None
    if not 1 <= number <= len(gifts): raise ValueError("선택 번호가 범위를 벗어났습니다")
    return number - 1

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(); p.add_argument("--ip", required=True); p.add_argument("--https-port", type=int, default=443)
    p.add_argument("--http-port", type=int, default=80)
    p.add_argument("--dns-port", type=int, default=53); p.add_argument("--select", default="ask")
    p.add_argument("--gifts", type=Path, default=ROOT/"배포파일"); p.add_argument("--keys", type=Path, default=ROOT/"keys"/"aes_keys.txt")
    p.add_argument("--cert", type=Path, default=ROOT/"certs"/"server.pem"); p.add_argument("--upstream", default="1.1.1.1")
    args = p.parse_args(argv); logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    gifts = load_gifts(args.gifts)
    state = GiftState(gifts, load_boss_key(args.keys), select_gift(gifts, args.select))
    dns_state = _DNS.DnsState(args.ip, args.upstream, args.upstream, LOCAL_HOSTS)
    udp = _DNS.ThreadingUdpServer(("0.0.0.0", args.dns_port), _DNS.DnsUdpHandler); tcp = _DNS.ThreadingTcpServer(("0.0.0.0", args.dns_port), _DNS.DnsTcpHandler)
    udp.state = tcp.state = dns_state
    plain = ThreadingHTTPServer(("0.0.0.0", args.http_port), Handler); plain.state = state
    httpd = ThreadingHTTPServer(("0.0.0.0", args.https_port), Handler); httpd.state = state
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.minimum_version = ssl.TLSVersion.TLSv1
    context.set_ciphers("DEFAULT:@SECLEVEL=0"); context.load_cert_chain(args.cert); httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (udp, tcp, plain, httpd)]
    for t in threads: t.start()
    print(f"DNS {args.ip}:{args.dns_port} / HTTP {args.ip}:{args.http_port} / HTTPS {args.ip}:{args.https_port}\n지원: X / Y / Omega Ruby / Alpha Sapphire (Korean)\n종료: Ctrl+C")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt: pass
    finally:
        for s in (udp, tcp, plain, httpd): s.shutdown(); s.server_close()
    return 0
if __name__ == "__main__": raise SystemExit(main())
