"""Inspect archived pages and GET APIs against an isolated copy of the save DB."""
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, unquote

ROOT = Path(__file__).resolve().parents[1]


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ("src", "href", "data", "action") and value:
                self.links.append(value)


def probe():
    sys.argv = [sys.argv[0]]
    sys.path.insert(0, str(ROOT))
    from utils import save_data, managers
    from api.server import app, SITE_DIR, UNAVAILABLE_DECORATIONS
    from api.routes import GET_RESPONSES
    managers.chest.update_json()
    managers.crops.update_json()
    client = app.test_client()
    report = {"pages": [], "apis": [], "missing": [], "external": [], "missing_illustrations": []}
    targets = set()
    for page in SITE_DIR.rglob("*.html"):
        path = "/" + page.relative_to(SITE_DIR).as_posix()
        response = client.get(path)
        report["pages"].append({"path": path, "status": response.status_code})
        parser = Links()
        parser.feed(response.get_data(as_text=True))
        report["missing_illustrations"].extend(re.findall(r'data-pdw-missing="([^"]+)"', response.get_data(as_text=True)))
        for ref in parser.links:
            absolute = urljoin("http://127.0.0.1:8080" + path, ref)
            url = urlsplit(absolute)
            if url.scheme not in ("http", "https"):
                continue
            if url.hostname not in ("127.0.0.1", "localhost"):
                report["external"].append({"page": path, "url": absolute})
                continue
            if url.path:
                targets.add(unquote(url.path))
    pending = list(targets)
    checked = set()
    while pending:
        path = pending.pop()
        if path in checked:
            continue
        checked.add(path)
        response = client.get(path, follow_redirects=True)
        if response.status_code >= 400:
            report["missing"].append({"path": path, "status": response.status_code})
            continue
        if path.endswith(".css"):
            stylesheet = response.data.decode("utf-8", errors="replace")
            stylesheet = re.sub(r"/\*.*?\*/", "", stylesheet, flags=re.S)
            for ref in re.findall(r'url\(\s*[\x22\x27]?([^\x22\x27\s)]+)', stylesheet):
                url = urlsplit(urljoin("http://127.0.0.1:8080" + path, ref))
                if url.hostname in ("127.0.0.1", "localhost"):
                    pending.append(unquote(url.path))
    report["resources_checked"] = len(checked)
    report["unavailable_decorations"] = sorted(UNAVAILABLE_DECORATIONS)
    for name in GET_RESPONSES:
        # Mutation endpoints are covered separately by flow tests.
        if any(word in name for word in ("update", "end", "start", "delete", "regist", "my_state", "tutorial")):
            continue
        response = client.get("/api/", query_string={"p": name})
        report["apis"].append({"api": name, "status": response.status_code})
    print("AUDIT_JSON=" + json.dumps(report, ensure_ascii=True))


def main():
    if "--probe" in sys.argv:
        probe()
        return
    with tempfile.TemporaryDirectory(prefix="pdw-audit-") as temp:
        temp = Path(temp)
        source = ROOT / "save_data" / "pokemon_saves.db"
        with sqlite3.connect(source) as src, sqlite3.connect(temp / source.name) as dst:
            src.backup(dst)
        src.close()
        dst.close()
        (temp / "gscd.txt").write_bytes((ROOT / "save_data" / "gscd.txt").read_bytes())
        env = {**os.environ, "PDW_SAVE_DIR": str(temp)}
        result = subprocess.run([sys.executable, __file__, "--probe"], cwd=ROOT, env=env, text=True, capture_output=True)
        if result.returncode:
            print(result.stderr)
            raise SystemExit(result.returncode)
        line = next(line for line in result.stdout.splitlines() if line.startswith("AUDIT_JSON="))
        report = json.loads(line.split("=", 1)[1])
        report_dir = ROOT / "audit_reports"
        report_dir.mkdir(exist_ok=True)
        output = report_dir / "site-audit.json"
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"pages":len(report["pages"]), "apis":len(report["apis"]), "resources_checked":report["resources_checked"], "api_failures":[x for x in report["apis"] if x["status"] >= 400], "missing": report["missing"], "unavailable_illustrations":len(set(report["missing_illustrations"])), "external_count":len(report["external"]), "report":str(output)}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
