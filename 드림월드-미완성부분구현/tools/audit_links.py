"""실제 연결을 재귀 검사한다. 숨겨진 누락 그림도 별도로 실패 처리한다."""
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
from collections import deque
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, unquote

ROOT = Path(__file__).resolve().parents[1]


class References(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []
        self.missing = []
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        for key in ("href", "src", "data", "poster"):
            if values.get(key):
                self.refs.append((tag, values[key]))
        for candidate in values.get("srcset", "").split(","):
            if candidate.strip():
                self.refs.append(("img", candidate.strip().split()[0]))
        if "data-pdw-missing" in values:
            self.missing.append(values["data-pdw-missing"])


def probe():
    sys.argv = [sys.argv[0]]
    sys.path.insert(0, str(ROOT))
    from api.server import app, SITE_DIR
    from game_sync_server.entralinked.utility.db_manager import db
    app.logger.disabled = True
    client = app.test_client()
    queue = deque(("/", "/local/", "/local/customize", "/pdw/", "/support/"))
    queue.extend("/" + p.relative_to(SITE_DIR).as_posix() for p in SITE_DIR.rglob("*.html"))
    report = {"pages": [], "resources": [], "failures": [], "unavailable_images": [], "external": [], "fragments": [], "placeholder_assets": []}
    seen, parents, ids = set(), {}, {}
    def enqueue(ref, base, kind):
        url = urlsplit(urljoin("http://localhost" + base, ref))
        if url.scheme not in ("http", "https"):
            return
        if url.hostname not in ("localhost", "127.0.0.1"):
            report["external"].append({"page": base, "url": url.geturl()})
            return
        # 링크의 GET 요청으로 게임 진행 상태를 바꾸지 않는다.
        path = url.path or "/"
        if path.startswith("/api/"):
            return
        if url.fragment and kind == "a":
            report["fragments"].append({"source": base, "path": path, "id": unquote(url.fragment)})
        parents.setdefault(path, base)
        queue.append(path)
    while queue:
        path = queue.popleft()
        if path in seen:
            continue
        seen.add(path)
        if len(seen) > 15000:
            raise RuntimeError("링크 순환 또는 점검 한도 초과")
        response = client.get(path, follow_redirects=True)
        record = {"path": path, "status": response.status_code, "from": parents.get(path), "bytes": len(response.data)}
        if response.status_code >= 400 or not response.data:
            report["failures"].append(record)
            continue
        ctype = response.content_type or ""
        if b"AUTO-GENERATED PGL STUB" in response.data:
            report["placeholder_assets"].append({**record, "reason": "보관본의 임시 대체 파일"})
        elif ctype.startswith("image/") and len(response.data) <= 100:
            report["placeholder_assets"].append({**record, "reason": "100바이트 이하 이미지: 간격용 파일 또는 임시 이미지인지 원본 확인 필요"})
        if "text/html" in ctype:
            report["pages"].append(record)
            text = response.data.decode("utf-8", errors="replace")
            parser = References()
            parser.feed(text)
            ids[path] = set(re.findall(r'(?:id|name)=[\x22\x27]([^\x22\x27]+)', text))
            report["unavailable_images"].extend({"page": path, "path": p} for p in parser.missing)
            for kind, ref in parser.refs:
                enqueue(ref, response.request.path, kind)
            for ref in re.findall(r'(?:window\.open|location\.href\s*=)\s*\(?\s*[\x22\x27]([^\x22\x27]+)', text):
                enqueue(ref, path, "a")
        else:
            report["resources"].append(record)
        if "text/css" in ctype or "text/html" in ctype:
            text = re.sub(r"/\*.*?\*/", "", response.data.decode("utf-8", errors="replace"), flags=re.S)
            for ref in re.findall(r'url\(\s*[\x22\x27]?([^\x22\x27\s)]+)', text):
                enqueue(ref, response.request.path, "css")
            if "text/css" in ctype:
                for ref in re.findall(r'@import\s+[\x22\x27]([^\x22\x27]+)', text):
                    enqueue(ref, response.request.path, "css")
    report["spa_routes"] = [r for r in report["fragments"] if r["id"].startswith("/")]
    report["broken_fragments"] = [r for r in report["fragments"] if not r["id"].startswith("/") and r["path"] in ids and r["id"] not in ids[r["path"]]]
    del report["fragments"]
    if os.environ.get("PDW_AUDIT_ALL_IMAGES") == "1":
        from api.archive import inventory
        items = inventory()[0]
        failures = []
        page_count = max(1, (len(items) + 39) // 40)
        for page in range(1, page_count + 1):
            response = client.get("/local/gallery", query_string={"page": page})
            if response.status_code != 200:
                failures.append({"page": page, "status": response.status_code})
            response.close()
        for key in items:
            response = client.get("/local/gallery/" + key)
            if response.status_code != 200 or ("/local/image/" + key).encode() not in response.data:
                failures.append({"detail": key, "status": response.status_code})
            response.close()
            response = client.get("/local/image/" + key)
            if response.status_code != 200 or not response.content_type.startswith("image/") or len(response.data) <= 100:
                failures.append({"image": key, "status": response.status_code})
            response.close()
        report["gallery"] = {"items_checked": len(items), "pages_checked": page_count, "failures": failures}
    db.close()
    print("LINK_AUDIT=" + json.dumps(report, ensure_ascii=True))


def main():
    if "--probe" in sys.argv:
        probe()
        return
    with tempfile.TemporaryDirectory(prefix="pdw-links-") as temp:
        temp = Path(temp)
        source = ROOT / "save_data/pokemon_saves.db"
        with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True) as src, sqlite3.connect(temp / source.name) as dst:
            src.backup(dst)
        src.close()
        dst.close()
        (temp / "gscd.txt").write_bytes((ROOT / "save_data/gscd.txt").read_bytes())
        env = {**os.environ, "PDW_SAVE_DIR": str(temp), "PDW_AUDIT_ALL_IMAGES": "1" if "--all-images" in sys.argv else "0"}
        result = subprocess.run([sys.executable, __file__, "--probe"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
        if result.returncode:
            raise RuntimeError(result.stderr[-6000:])
        report = json.loads(next(s for s in result.stdout.splitlines() if s.startswith("LINK_AUDIT=")).split("=", 1)[1])
        output = ROOT / "audit_reports/recursive-links.json"
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k: len(v) if isinstance(v, list) else v for k, v in report.items()}, ensure_ascii=True))
        print(json.dumps(report["failures"][:40], ensure_ascii=True))


if __name__ == "__main__":
    main()
