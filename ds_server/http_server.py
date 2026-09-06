from __future__ import annotations

import base64
import hashlib
import html
import ipaddress
import json
import re
import threading
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .gift_converter import (
    gen4_pcd_to_dls,
    gen5_pgf_to_dls,
    gift_metadata,
    version_mask,
)
from .packet_log import PacketLog, safe_fields
from .pokemon import build_gts_result_packet, decode_gts_upload, pk4_metadata
from .protocol import decode_dls_form, language_attr
from .state import ServerState


TOKEN = "c9KcX1Cry3QKS2Ai7yxL6QiQGeBGeQKR"
GEN4_GAME_CODES = {
    "ADAD", "ADAE", "ADAF", "ADAI", "ADAJ", "ADAK", "ADAS",
    "CPUD", "CPUE", "CPUF", "CPUI", "CPUJ", "CPUK", "CPUS",
    "IPGD", "IPGE", "IPGF", "IPGI", "IPGJ", "IPGK", "IPGS",
}


PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DS Pokémon 배포 서버</title>
<style>
:root{color-scheme:dark;--bg:#0c1220;--card:#151f33;--line:#2d3b58;--text:#edf3ff;--muted:#9db0ce;--accent:#68d391;--warn:#f6ad55}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(135deg,#0a1020,#111a2c);font:15px/1.5 system-ui,sans-serif;color:var(--text)}
main{max-width:980px;margin:auto;padding:34px 18px 60px}h1{font-size:28px;margin:0 0 6px}h2{font-size:18px;margin:0 0 12px}.lead{color:var(--muted);margin:0 0 24px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:16px}.card{background:rgba(21,31,51,.96);border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:0 12px 28px #0005}
label{display:block;color:var(--muted);font-size:13px;margin-top:10px}input,select,textarea,button{width:100%;border:1px solid var(--line);border-radius:8px;background:#0d1628;color:var(--text);padding:9px;margin-top:4px}
textarea{min-height:72px}button{background:#245c42;border-color:#327a58;font-weight:700;cursor:pointer;margin-top:14px}button.secondary{background:#29344a;border-color:#43516c}.status{white-space:pre-wrap;color:var(--muted);font-size:13px;margin-top:12px}.ok{color:var(--accent)}.warning{color:var(--warn)}
code{background:#0a1120;padding:2px 5px;border-radius:4px}.wide{grid-column:1/-1}table{width:100%;border-collapse:collapse}td{border-top:1px solid var(--line);padding:8px 4px;vertical-align:top}td:first-child{color:var(--muted);width:150px}
</style></head><body><main>
<h1>DS Pokémon Private Distribution</h1><p class="lead">PKHeX 파일을 올리고 Nintendo DS에서 받을 항목을 선택합니다.</p>
<section class="card wide"><h2>서버 상태</h2><table id="state"><tr><td>불러오는 중</td><td>...</td></tr></table><button class="secondary" onclick="refresh()">새로고침</button></section>
<div class="grid">
<section class="card"><h2>4세대 GTS로 Pokémon 보내기</h2>
<label>PKHeX .pk4/.pkm (136 또는 236바이트)<input id="pokemonFile" type="file" accept=".pk4,.pkm"></label>
<label>136바이트 파일의 표시 레벨<input id="pokemonLevel" type="number" min="1" max="100" value="50"></label>
<button onclick="uploadPokemon()">GTS 배포 활성화</button><div id="pokemonMsg" class="status"></div></section>
<section class="card"><h2>4세대 미스터리 기프트</h2>
<label>PKHeX .pcd 또는 배포용 .myg<input id="gen4File" type="file" accept=".pcd,.myg"></label>
<button onclick="uploadGift(4)">4세대 배포 활성화</button><div id="gen4Msg" class="status"></div></section>
<section class="card"><h2>5세대 미스터리 기프트</h2>
<label>PKHeX .pgf 또는 배포용 .bin<input id="gen5File" type="file" accept=".pgf,.bin"></label>
<label>수신 언어<select id="language"><option value="k">한국어</option><option value="e">영어</option><option value="j">일본어</option><option value="f">프랑스어</option><option value="g">독일어</option><option value="i">이탈리아어</option><option value="s">스페인어</option></select></label>
<label>허용 버전<input id="versions" value="wbw2b2" placeholder="예: bw 또는 b2w2"></label>
<label>다운로드 설명<textarea id="description">개인 배포 포켓몬입니다.</textarea></label>
<button onclick="uploadGift(5)">5세대 배포 활성화</button><div id="gen5Msg" class="status"></div></section>
<section class="card"><h2>패킷 분석</h2><p class="status">DNS/HTTP 요청은 <code>logs/packets.jsonl</code>에 저장됩니다. 인증 토큰은 요약 화면에서 해시 처리됩니다.</p>
<button class="secondary" onclick="clearSlot('pokemon')">GTS 배포 끄기</button><button class="secondary" onclick="clearSlot('gen4_gift')">4세대 선물 끄기</button><button class="secondary" onclick="clearSlot('gen5_gift')">5세대 선물 끄기</button></section>
</div>
<section class="card wide" style="margin-top:16px"><h2>중요</h2><p class="warning">종료된 Nintendo WFC의 인증/HTTPS는 이 앱만으로 복원되지 않습니다. 정품 카트리지는 호환 WFC DNS 또는 NoSSL 패치가 필요할 수 있습니다. 본인 소유 게임과 로컬 네트워크에서 사용하세요.</p></section>
</main><script>
async function fileB64(input){const f=input.files[0];if(!f)throw Error('파일을 선택하세요.');const b=new Uint8Array(await f.arrayBuffer());let s='';for(let i=0;i<b.length;i+=32768)s+=String.fromCharCode(...b.subarray(i,i+32768));return {name:f.name,data:btoa(s)}}
async function send(payload,msg){msg.textContent='처리 중...';try{const r=await fetch('/admin/upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const j=await r.json();if(!r.ok)throw Error(j.error||r.statusText);msg.textContent=JSON.stringify(j,null,2);msg.className='status ok';await refresh()}catch(e){msg.textContent=e.message;msg.className='status warning'}}
async function uploadPokemon(){const f=await fileB64(document.querySelector('#pokemonFile'));send({kind:'pokemon',file_name:f.name,data_base64:f.data,level:+document.querySelector('#pokemonLevel').value},document.querySelector('#pokemonMsg'))}
async function uploadGift(gen){const input=document.querySelector(gen===4?'#gen4File':'#gen5File');const f=await fileB64(input);const p={kind:'gen'+gen,file_name:f.name,data_base64:f.data};if(gen===5)Object.assign(p,{language:document.querySelector('#language').value,versions:document.querySelector('#versions').value,description:document.querySelector('#description').value});send(p,document.querySelector('#gen'+gen+'Msg'))}
async function clearSlot(slot){await fetch('/admin/clear',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({slot})});refresh()}
async function refresh(){const r=await fetch('/api/state');const j=await r.json();const names={pokemon:'GTS Pokémon',gen4_gift:'4세대 선물',gen5_gift:'5세대 선물'};document.querySelector('#state').innerHTML=Object.entries(names).map(([k,n])=>`<tr><td>${n}</td><td>${j.state[k]?escapeHtml(JSON.stringify(j.state[k])):'비활성'}</td></tr>`).join('')+`<tr><td>DS용 DNS</td><td>${j.public_ip}</td></tr>`}
function escapeHtml(s){return s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}refresh()
</script></body></html>"""


def _safe_name(name: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._")
    return clean[:100] or "upload.bin"


def _is_loopback(address: str) -> bool:
    return address in {"127.0.0.1", "::1"} or address.startswith("127.")


def _is_local_client(address: str) -> bool:
    try:
        value = ipaddress.ip_address(address)
    except ValueError:
        return False
    return value.is_loopback or value.is_private or value.is_link_local


class DsHttpServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self, address: tuple[str, int], root: Path, public_ip: str,
        packet_log: PacketLog, admin_loopback_only: bool,
        local_clients_only: bool = True,
    ) -> None:
        super().__init__(address, DsRequestHandler)
        self.root = root
        self.state = ServerState(root)
        self.public_ip = public_ip
        self.packet_log = packet_log
        self.admin_loopback_only = admin_loopback_only
        self.local_clients_only = local_clients_only


class DsRequestHandler(BaseHTTPRequestHandler):
    server: DsHttpServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send(self, body: bytes | str = b"", status: int = 200, headers: dict[str, str] | None = None) -> None:
        payload = body.encode("utf-8") if isinstance(body, str) else body
        is_dls = urlsplit(self.path).path == "/download"
        if is_dls:
            # Preserve the standalone DLS server's HTTP version and single Server header.
            self.protocol_version = "HTTP/1.0"
            self.send_response_only(status)
            self.send_header("Date", self.date_time_string())
        else:
            self.send_response(status)
        supplied = {key.lower() for key in (headers or {})}
        if "content-type" not in supplied:
            self.send_header("Content-Type", "text/plain; charset=utf-8")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _json(self, value: Any, status: int = 200) -> None:
        self._send(
            json.dumps(value, ensure_ascii=False, indent=2), status,
            {"Content-Type": "application/json; charset=utf-8"},
        )

    def _admin_allowed(self) -> bool:
        return not self.server.admin_loopback_only or _is_loopback(self.client_address[0])

    def _client_ip(self) -> str:
        address = self.client_address[0]
        if _is_loopback(address):
            forwarded = self.headers.get("X-DS-Client-IP", "")
            try:
                if forwarded and _is_local_client(forwarded):
                    return str(ipaddress.ip_address(forwarded))
            except ValueError:
                pass
        return address

    def _client_allowed(self) -> bool:
        return not self.server.local_clients_only or _is_local_client(self._client_ip())

    def _legacy_headers(self) -> dict[str, str]:
        return {
            "Server": "Microsoft-IIS/6.0", "P3P": "CP='NOI ADMa OUR STP'",
            "X-Powered-By": "ASP.NET", "Content-Type": "text/html",
            "Cache-Control": "private",
        }

    def _dls_headers(self, content_type: str = "text/plain") -> dict[str, str]:
        port = self.server.server_address[1]
        suffix = "" if port == 80 else f":{port}"
        return {
            "Server": "Nintendo Wii (http)", "Content-Type": content_type,
            "X-DLS-Host": "http://127.0.0.1/",
        }

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 8 * 1024 * 1024:
            raise ValueError("request body is too large")
        return self.rfile.read(length)

    def do_GET(self) -> None:
        split = urlsplit(self.path)
        client_ip = self._client_ip()
        if not self._client_allowed():
            self.server.packet_log.write(
                "blocked_http", client=client_ip, method="GET", path=split.path,
            )
            self._send("local network only", 403)
            return
        query = parse_qs(split.query, keep_blank_values=True)
        self.server.packet_log.write(
            "http", raw=self.requestline.encode(), client=client_ip,
            method="GET", path=split.path, query_keys=sorted(query),
        )
        if split.path == "/":
            if not self._admin_allowed():
                self._send("관리 화면은 서버 PC에서만 열 수 있습니다.", 403)
            else:
                self._send(PAGE, headers={"Content-Type": "text/html; charset=utf-8"})
            return
        if split.path == "/api/state":
            if not self._admin_allowed():
                self._json({"error": "loopback only"}, 403)
            else:
                self._json({"state": self.server.state.snapshot(), "public_ip": self.server.public_ip})
            return
        if split.path.startswith("/pokemondpds/"):
            self._handle_gts(split.path, query)
            return
        self._send("not found", 404)

    def do_POST(self) -> None:
        split = urlsplit(self.path)
        client_ip = self._client_ip()
        if not self._client_allowed():
            self.server.packet_log.write(
                "blocked_http", client=client_ip, method="POST", path=split.path,
            )
            self._send("local network only", 403)
            return
        try:
            body = self._read_body()
        except ValueError as exc:
            self._json({"error": str(exc)}, 413)
            return
        self.server.packet_log.write(
            "http", raw=body, client=client_ip, method="POST",
            path=split.path, content_type=self.headers.get("Content-Type", ""),
        )
        if split.path == "/download":
            self._handle_dls(body)
            return
        if split.path == "/admin/upload":
            self._handle_admin_upload(body)
            return
        if split.path == "/admin/clear":
            self._handle_admin_clear(body)
            return
        self._send("not found", 404)

    def _handle_gts(self, path: str, query: dict[str, list[str]]) -> None:
        if len(query) == 1:
            self._send(TOKEN, headers=self._legacy_headers())
            return
        if path.endswith("/info.asp"):
            self._send(b"\x01\x00", headers=self._legacy_headers())
        elif path.endswith("/setProfile.asp"):
            self._send(b"\x00" * 8, headers=self._legacy_headers())
        elif path.endswith("/post.asp"):
            encoded = query.get("data", [""])[0]
            try:
                clear = decode_gts_upload(encoded)
                digest = hashlib.sha256(clear).hexdigest()[:12]
                name = f"received_{datetime.now():%Y%m%d_%H%M%S}_{digest}.pk4"
                (self.server.state.received_dir / name).write_bytes(clear)
                self.server.packet_log.write("gts_upload", raw=clear, file=name, **pk4_metadata(clear))
                self._send(b"\x0c\x00", headers=self._legacy_headers())
            except Exception as exc:
                self.server.packet_log.write("gts_error", error=str(exc))
                self._send(b"\x0c\x00", headers=self._legacy_headers())
        elif path.endswith("/result.asp"):
            active = self.server.state.get_item("pokemon")
            file_path = self.server.state.file_for("pokemon")
            if not active or not file_path:
                self._send(b"\x05\x00", headers=self._legacy_headers())
                return
            try:
                packet = build_gts_result_packet(file_path.read_bytes(), int(active.get("level", 50)))
                self.server.packet_log.write("gts_distribution", raw=packet, source=active["source_name"])
                self._send(packet, headers=self._legacy_headers())
            except Exception as exc:
                self.server.packet_log.write("gts_error", error=str(exc))
                self._send(b"\x05\x00", headers=self._legacy_headers())
        elif path.endswith("/delete.asp"):
            self._send(b"\x01\x00", headers=self._legacy_headers())
        elif path.endswith("/search.asp"):
            self._send(b"", headers=self._legacy_headers())
        else:
            self._send("", 404, self._legacy_headers())

    def _handle_dls(self, body: bytes) -> None:
        try:
            fields = decode_dls_form(body)
            action = fields.get("action", "").lower()
            game_code = fields.get("gamecd", "").upper()
            gen = 5 if game_code.startswith("IRA") else 4
            slot = f"gen{gen}_gift"
            active = self.server.state.get_item(slot)
            file_path = self.server.state.file_for(slot)
            self.server.packet_log.write(
                "dls", raw=body, action=action, generation=gen,
                fields=safe_fields(fields), client=self._client_ip(),
            )
            if action == "count":
                self._send("1" if active and file_path else "0", headers=self._dls_headers())
                return
            if action == "list":
                if not active or not file_path:
                    self._send("\r\n", headers=self._dls_headers())
                    return
                if gen == 5:
                    line = (
                        f"{active['wire_name']}\t\tMYSTERY_{active['language_attr']}\t"
                        f"{active['version_mask']:06X}\t\t{file_path.stat().st_size}\r\n"
                    )
                else:
                    line = f"{active['wire_name']}\t\t\t\t\t{file_path.stat().st_size}\r\n"
                self._send(line, headers=self._dls_headers())
                return
            if action == "contents" and active and file_path:
                headers = self._dls_headers("application/x-dsdl")
                headers["Content-Disposition"] = f"attachment; filename=\"{active['wire_name']}\""
                payload = file_path.read_bytes()
                self.server.packet_log.write("dls_distribution", raw=payload, generation=gen, source=active["source_name"])
                self._send(payload, headers=headers)
                return
            self._send("", 404 if action == "contents" else 200, self._dls_headers())
        except Exception as exc:
            self.server.packet_log.write("dls_error", raw=body, error=str(exc))
            self._send("", 500, self._dls_headers())

    def _handle_admin_upload(self, body: bytes) -> None:
        if not self._admin_allowed():
            self._json({"error": "관리 API는 서버 PC에서만 사용할 수 있습니다."}, 403)
            return
        try:
            request = json.loads(body)
            source_name = _safe_name(str(request["file_name"]))
            data = base64.b64decode(request["data_base64"], validate=True)
            kind = request["kind"]
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            if kind == "pokemon":
                level = int(request.get("level", 50))
                meta = pk4_metadata(data, level)
                extension = Path(source_name).suffix.lower()
                if extension not in {".pk4", ".pkm"}:
                    raise ValueError("4세대 .pk4 또는 .pkm 파일을 선택하세요.")
                target = self.server.state.upload_dir / f"{stamp}_{source_name}"
                target.write_bytes(data)
                item = {
                    "source_name": source_name, "path": target.relative_to(self.server.root).as_posix(),
                    "level": level, **meta,
                }
                self.server.state.set_item("pokemon", item)
                self._json({"ok": True, "slot": "pokemon", "metadata": meta})
                return
            if kind == "gen4":
                wire = gen4_pcd_to_dls(data)
                meta = gift_metadata(wire)
                wire_name = f"card_{meta['card_id']:04d}.myg"
                target = self.server.state.upload_dir / f"{stamp}_{wire_name}"
                target.write_bytes(wire)
                item = {
                    "source_name": source_name, "wire_name": wire_name,
                    "path": target.relative_to(self.server.root).as_posix(), **meta,
                }
                self.server.state.set_item("gen4_gift", item)
                self._json({"ok": True, "slot": "gen4_gift", "metadata": meta})
                return
            if kind == "gen5":
                language = str(request.get("language", "e")).lower()
                versions = str(request.get("versions", "wbw2b2"))
                wire = gen5_pgf_to_dls(data, str(request.get("description", "")), language, versions)
                meta = gift_metadata(wire)
                mask = version_mask(versions) if len(data) == 204 else int.from_bytes(wire[0xCC:0xD0], "little")
                wire_name = f"G{meta['card_id']:04d}.bin"
                target = self.server.state.upload_dir / f"{stamp}_{wire_name}"
                target.write_bytes(wire)
                item = {
                    "source_name": source_name, "wire_name": wire_name,
                    "path": target.relative_to(self.server.root).as_posix(),
                    "language": language, "language_attr": language_attr(wire[0x2CB]),
                    "version_mask": mask, **meta,
                }
                self.server.state.set_item("gen5_gift", item)
                self._json({"ok": True, "slot": "gen5_gift", "metadata": meta})
                return
            raise ValueError("알 수 없는 업로드 종류입니다.")
        except Exception as exc:
            self._json({"error": str(exc)}, 400)

    def _handle_admin_clear(self, body: bytes) -> None:
        if not self._admin_allowed():
            self._json({"error": "loopback only"}, 403)
            return
        try:
            slot = json.loads(body)["slot"]
            self.server.state.set_item(slot, None)
            self._json({"ok": True, "slot": slot})
        except Exception as exc:
            self._json({"error": str(exc)}, 400)
