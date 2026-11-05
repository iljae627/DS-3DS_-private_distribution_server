"""누락 파일만 복구하고 저장 데이터와 변경된 소스를 보존한다."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
from urllib.request import Request, urlopen
from urllib.parse import quote
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = ("드림월드", "드림월드-미완성부분구현")


def fetch(url):
    with urlopen(Request(url, headers={"User-Agent": "PDW-recovery"}), timeout=60) as response:
        return response.read()


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def snapshot():
    target = ROOT / "드림월드-복구도구" / "backups" / datetime.now().strftime("%Y%m%d-%H%M%S")
    target.mkdir(parents=True)
    with ZipFile(target / "sources-and-saves.zip", "w", ZIP_DEFLATED) as archive:
        for folder in FOLDERS:
            for path in (ROOT / folder).rglob("*"):
                if not path.is_file() or any(part in {".venv", ".research", "__pycache__", "dreamworld_assets", ".git"} for part in path.relative_to(ROOT / folder).parts):
                    continue
                if path.suffix == ".db":
                    backup = target / (folder + "-" + path.name)
                    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as src, sqlite3.connect(backup) as dst:
                        src.backup(dst)
                    src.close()
                    dst.close()
                    archive.write(backup, path.relative_to(ROOT).as_posix())
                elif not path.name.endswith(("-wal", "-shm")):
                    archive.write(path, path.relative_to(ROOT).as_posix())
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore", action="store_true", help="누락 파일 복구 (기존 파일 덮어쓰기 없음)")
    parser.add_argument("--verify-hashes", action="store_true", help="존재하는 파일의 Git 객체 해시도 비교 (차이는 덮어쓰지 않음)")
    args = parser.parse_args()
    report = {"folders": {}, "restored": []}
    if args.restore:
        report["backup"] = str(snapshot())
    for folder in FOLDERS:
        entries = git("ls-tree", "-rz", "HEAD", "--", folder).split(b"\0")
        missing = []
        for entry in entries:
            if not entry:
                continue
            meta, name = entry.split(b"\t", 1)
            path = ROOT / name.decode("utf-8")
            if not path.exists() and meta.split()[1] == b"blob":
                missing.append(str(path.relative_to(ROOT)))
                if args.restore:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(git("cat-file", "blob", meta.split()[2].decode()))
                    report["restored"].append(str(path.relative_to(ROOT)))
        report["folders"][folder] = {"git_missing": missing, "upstream": []}
    tree = json.loads(fetch("https://api.github.com/repos/minibug1021/dreamworld-reawakened/git/trees/main?recursive=1"))
    sources = [("minibug1021/dreamworld-reawakened", tree["sha"], "", tree)]
    for entry in tree["tree"]:
        if entry["type"] == "commit" and entry["path"] in ("dreamworld_assets", "game_sync_server"):
            repo = "minibug1021/" + {"dreamworld_assets": "dreamworld-assets", "game_sync_server": "game-sync-python"}[entry["path"]]
            subtree = json.loads(fetch(f"https://api.github.com/repos/{repo}/git/trees/{entry['sha']}?recursive=1"))
            sources.append((repo, entry["sha"], entry["path"] + "/", subtree))
    tasks = []
    for repo, commit, prefix, source in sources:
        if source.get("truncated"):
            raise RuntimeError("공개 원본 파일 목록이 잘려 검증할 수 없습니다.")
        for folder in FOLDERS:
            missing = [e for e in source["tree"] if e["type"] == "blob" and not (ROOT / folder / (prefix + e["path"])).is_file()]
            checked = {"repo": repo, "commit": commit, "files": sum(e["type"] == "blob" for e in source["tree"]), "missing": [prefix + e["path"] for e in missing]}
            if args.verify_hashes:
                changed = []
                for entry in source["tree"]:
                    path = ROOT / folder / (prefix + entry["path"])
                    if entry["type"] != "blob" or not path.is_file():
                        continue
                    data = path.read_bytes()
                    actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
                    if actual != entry["sha"]:
                        changed.append(prefix + entry["path"])
                checked["modified_preserved"] = changed
            report["folders"][folder]["upstream"].append(checked)
            for entry in missing:
                tasks.append((folder, repo, commit, prefix, entry))
    def recover(task):
        folder, repo, commit, prefix, entry = task
        destination = ROOT / folder / (prefix + entry["path"])
        data = fetch(f"https://raw.githubusercontent.com/{repo}/{commit}/" + quote(entry["path"], safe="/"))
        if hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() != entry["sha"]:
            raise ValueError("원본 Git 해시 불일치: " + entry["path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as output:
            output.write(data)
        return str(destination.relative_to(ROOT))
    if args.restore:
        with ThreadPoolExecutor(max_workers=6) as pool:
            report["restored"].extend(pool.map(recover, tasks))
    report_path = ROOT / "드림월드-복구도구" / ("integrity.json" if args.verify_hashes else "restoration.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(report_path), "restored": len(report["restored"]), "folders": {name: {"git_missing": len(data["git_missing"]), "sources": [{"repo": source["repo"], "files": source["files"], "missing": len(source["missing"]), "modified_preserved": len(source.get("modified_preserved", []))} for source in data["upstream"]]} for name, data in report["folders"].items()}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
