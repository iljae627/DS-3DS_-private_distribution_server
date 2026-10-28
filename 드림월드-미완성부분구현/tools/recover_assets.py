"""Restore missing archive files from the public Dream World Revival tree.

Only missing paths from our audit report are eligible. Existing files are never
overwritten. Every download is pinned to a commit and recorded with SHA-256.
"""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
REPO = "Shade-of-Gr3y/Dream-World-Revival"


def fetch(url):
    with urlopen(Request(url, headers={"User-Agent": "PDW-local-asset-audit"}), timeout=40) as response:
        return response.read()


def main():
    tree = json.loads(fetch(f"https://api.github.com/repos/{REPO}/git/trees/main?recursive=1"))
    sha = tree["sha"]
    entries = [item["path"] for item in tree["tree"] if item["type"] == "blob"]
    report = json.loads((ROOT / "audit_reports/site-audit.json").read_text(encoding="utf-8"))
    manifest_path = ROOT / "audit_reports/recovered-assets.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
    recovered_swfs = {
        "catalogimg_1.swf": "Completed Assets/Catalogue, Decor and Plushies/Catalogue/catalogimg_1.swf",
        "301.swf": "File Extraction/301/301.swf",
    }
    for filename, source in recovered_swfs.items():
        destination = ROOT / "dreamworld_assets/shared.pokemon-gl.com/src/swf/theme/assets/global/parts/interior" / filename
        data = fetch(f"https://raw.githubusercontent.com/{REPO}/{sha}/" + quote(source, safe="/"))
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        if destination.read_bytes() != data:
            raise ValueError(f"An existing asset differs from the archive: {destination}")
        local_path = destination.relative_to(ROOT).as_posix()
        if not any(item["local"] == local_path for item in manifest):
            manifest.append({"local": local_path, "source": source, "commit": sha, "sha256": hashlib.sha256(data).hexdigest()})
    for missing in report["missing"]:
        path = missing["path"]
        if not path.startswith("/support/"):
            continue
        destination = ROOT / "dreamworld_assets/shared.pokemon-gl.com" / path.lstrip("/")
        if destination.exists():
            continue
        candidates = []
        for language in ("ko", "en", "ja", "de", "fr", "es", "it"):
            suffix = re.sub(r"/(ko|en|ja|de|fr|es|it)/", "/" + language + "/", path)
            candidates = [entry for entry in entries if entry.endswith(suffix)]
            if candidates:
                break
        if not candidates:
            continue
        source = sorted(candidates)[0]
        data = fetch(f"https://raw.githubusercontent.com/{REPO}/{sha}/" + quote(source, safe="/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        manifest.append({"local": destination.relative_to(ROOT).as_posix(), "source": source, "commit": sha, "sha256": hashlib.sha256(data).hexdigest()})
        print(path, len(data))
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Recovered files:", len(manifest))


if __name__ == "__main__":
    main()
