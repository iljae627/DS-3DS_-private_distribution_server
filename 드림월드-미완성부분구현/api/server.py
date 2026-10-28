import re
import os
import atexit
import logging
import mimetypes
from pathlib import Path
import json
from werkzeug.exceptions import HTTPException
from urllib.parse import parse_qs
from urllib.parse import urljoin, urlsplit, unquote
from html import escape
from flask import Flask, request, redirect, Response, abort

from utils import language
from utils.patch_file import apply_substitutions, get_cached, SWF_PATHS
from game_sync_server.entralinked.utility.db_manager import db
from api.routes import GET_RESPONSES, POST_RESPONSES
from api.local_pages import local

# ---------------
# Config
# ---------------

atexit.register(db.close)

PATCHED_SWFS = set(SWF_PATHS.keys())
LANG = language.player_language

ROOT_DIR   = Path(__file__).resolve().parent.parent
SITE_DIR   = ROOT_DIR / "dreamworld_assets" / f"{LANG}.pokemon-gl.com"
SHARED_DIR = ROOT_DIR / "dreamworld_assets" / "shared.pokemon-gl.com"

# file extensions that should be patched before serving
# binary assets (images, fonts, etc.) are served as-is
PATCHABLE_EXTENSIONS = {".js", ".html", ".css"}
UNAVAILABLE_DECORATIONS = set()

NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}

# ---------------
# App
# ---------------

app = Flask(__name__)
app.register_blueprint(local)
app.logger.setLevel(logging.INFO)

# ---------------
# Helpers
# ---------------

def read_and_patch(file_path: Path) -> bytes:
    data = file_path.read_bytes()

    if file_path.suffix.lower() in PATCHABLE_EXTENSIONS:
        data = apply_substitutions(data, file_path.name)
    if file_path.suffix.lower() == ".html" and "/support/" in request.path:
        def archived_image(match):
            markup = match[0].decode("utf-8")
            source = re.search(r'\bsrc=[\x22\x27]([^\x22\x27]+)', markup)
            if source is None:
                return match[0]
            url = urlsplit(urljoin(request.url, source[1]))
            if url.netloc != request.host or resolve_static(unquote(url.path)):
                return match[0]
            missing = escape(url.path, quote=True)
            return (f'<span data-pdw-missing="{missing}" style="display:inline-block;padding:10px;background:#fff3cf;color:#35424a">보관본에 이 설명 그림이 없습니다. <a href="/local/help">로컬 이용 안내 보기</a></span>').encode()
        data = re.sub(rb'<img\b[^>]*>', archived_image, data, flags=re.I)
    if file_path.suffix.lower() == ".css" and request.path.startswith("/support/"):
        def decorative_image(match):
            source = match[1].decode("utf-8", errors="replace")
            url = urlsplit(urljoin(request.url, source))
            if url.netloc == request.host and not resolve_static(unquote(url.path)):
                UNAVAILABLE_DECORATIONS.add(url.path)
                return b"none"
            return match[0]
        data = re.sub(rb'url\(\s*[\x22\x27]?([^\x22\x27\s)]+)[\x22\x27]?\s*\)', decorative_image, data)

    if file_path.suffix.lower() == ".xml":
        if "Basilisk" not in request.headers.get("User-Agent", ""):
            data = data.replace(b"&amp;#xD;", os.linesep.encode())

    return data

def send_file(file_path: Path) -> Response:
    data = read_and_patch(file_path)
    content_type, _ = mimetypes.guess_type(file_path)
    return Response(data, content_type=content_type or "application/octet-stream")

def send_bytes(data: bytes, content_type: str) -> Response:
    """Serve raw bytes for patched SWF assets."""
    return Response(data, content_type=content_type)

def resolve_static(path: str) -> Path | None:
    """Return the filesystem path for a static asset, checking site dir, then shared dir as a fallback."""
    relative = re.sub(r"^/(?:cdn2?|shared|ja|en|fr|it|de|es|ko)\.pokemon-gl\.com/?", "/", path).lstrip("/")
    if relative == "assets/global/images/dialog-close.png":
        relative = "src/swf/assets/global/images/dialog-close.png"
    if ".." in Path(relative).parts or "\\" in relative or ":" in relative:
        return None

    # site-specific first
    site_path = SITE_DIR / relative
    if site_path.is_file():
        return site_path

    # shared fallback, strip language prefix (e.g. /en/ → /)
    shared_relative = re.sub(r"/(ja|en|fr|it|de|es|ko)/", "/", relative)
    shared_path = SHARED_DIR / shared_relative
    if shared_path.is_file():
        return shared_path

    # Some languages were only partially archived. Serve the same resource
    # from the English/Japanese archive, including that language's path segment.
    for lang in dict.fromkeys((LANG, "en", "ja", "de", "fr", "es", "it")):
        localized = re.sub(r"(^|/)(ja|en|fr|it|de|es|ko)(?=/)", lambda m: m[1] + lang, relative)
        for root in (ROOT_DIR / "dreamworld_assets" / f"{lang}.pokemon-gl.com", SHARED_DIR):
            candidate = root / localized
            if candidate.is_file():
                return candidate

    # Some recovered catalogue builds request generated thumbnail names that
    # are absent from the archive.  The full-size SWF uses the same artwork and
    # is a safe local fallback.
    filename = shared_path.name
    aliases = []
    room = re.fullmatch(r"20[23]_([234])\.swf", filename)
    if room:
        aliases.append(shared_path.with_name(f"201_{room[1]}.swf"))
    match = re.fullmatch(r"(\d+)thumb\.swf", filename)
    if match:
        aliases.append(shared_path.with_name(f"{match.group(1)}.swf"))
    for alias in aliases:
        if alias.is_file():
            return alias

    return None


def not_found(path: str) -> Response:
    app.logger.info("404 %s", path)
    return Response("Error: Not found", status=404, content_type="text/html")

# ---------------
# Routes
# ---------------

@app.before_request
def rewrite_incoming_path():
    """Apply path rewrites and enforce trailing slash on directory paths."""
    path = request.path
    if path.rstrip("/") == "/customize":
        return redirect("/local/customize", 302)
    canonical = re.sub(r"^/(?:cdn2?|shared|ja|en|fr|it|de|es|ko)\.pokemon-gl\.com/?", "/", path)
    if canonical != path:
        query = request.query_string.decode()
        return redirect(canonical + ("?" + query if query else ""), 302)

    # enforce trailing slash for paths that map to a site directory
    if not path.endswith("/") and (SITE_DIR / path.lstrip("/")).is_dir():
        return redirect(f"{path}/", 301)


@app.route("/api/", methods=["GET"])
def api_get():
    query    = {k: v[0] for k, v in parse_qs(request.query_string.decode(), keep_blank_values=True).items()}
    api_name = query.get("p")
    app.logger.info("API GET: %s %s", api_name, query)

    if api_name not in GET_RESPONSES:
        app.logger.warning("Unknown API: %s", api_name)
        abort(501, description="현재 로컬 서버에서 지원하지 않는 API입니다.")

    return Response(GET_RESPONSES[api_name](query), content_type="application/json", headers=NO_CACHE_HEADERS)


@app.route("/api/", methods=["POST"])
def api_post():
    qs_params   = {k: v[0] for k, v in parse_qs(request.query_string.decode(), keep_blank_values=True).items()}
    body_params = {
        k: values[0] if len(values) == 1 else values
        for k, values in parse_qs(request.get_data(as_text=True), keep_blank_values=True).items()
    }
    query       = {**qs_params, **body_params}
    api_name    = query.get("p")
    app.logger.info("API POST: %s %s", api_name, query)

    handler = POST_RESPONSES.get(api_name) or GET_RESPONSES.get(api_name)
    if handler is None:
        app.logger.warning("Unknown API: %s", api_name)
        abort(501, description="현재 로컬 서버에서 지원하지 않는 API입니다.")

    return Response(handler(query), content_type="application/json", headers=NO_CACHE_HEADERS)


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def catch_all(path: str):
    if ".." in Path(path).parts or "\\" in path or ":" in path:
        return not_found(path)
    if path == "crossdomain.xml":
        return Response('<?xml version="1.0"?><cross-domain-policy><allow-access-from domain="localhost"/><allow-access-from domain="127.0.0.1"/></cross-domain-policy>', content_type="application/xml")
    if not path:
        from utils import save_data
        if not save_data.read_player_data().get("member"):
            return redirect("/local/")
    if "&" in path:
        path = path.split("&")[0]

    full_path = f"/{path}"
    filename  = Path(path).name

    # return patched SWFs from our cache
    if filename in PATCHED_SWFS:
        return send_bytes(get_cached(filename), "application/x-shockwave-flash")

    # find first HTML file inside given directory
    for root in (SITE_DIR, ROOT_DIR / "dreamworld_assets" / "en.pokemon-gl.com", ROOT_DIR / "dreamworld_assets" / "ja.pokemon-gl.com"):
        dir_path = root / path
        if dir_path.is_dir():
            index = dir_path / "index.html"
            if not index.is_file():
                index = next(iter(sorted(dir_path.glob("*.html"))), None)
            if index is not None:
                return send_file(index)

    # static asset
    file_path = resolve_static(full_path)
    if file_path is None:
        return not_found(full_path)

    return send_file(file_path)


@app.errorhandler(Exception)
def api_error(error):
    if not request.path.startswith("/api"):
        if isinstance(error, HTTPException):
            return error
        app.logger.exception("Page request failed")
        return Response("페이지 처리 중 오류가 발생했습니다. 서버 로그를 확인하세요.", status=500)
    if isinstance(error, (ValueError, KeyError, TypeError, StopIteration)):
        status = 400
        message = str(error)
    elif isinstance(error, HTTPException):
        status, message = error.code, error.description
    else:
        app.logger.exception("API request failed")
        status, message = 500, "서버 처리 오류가 발생했습니다."
    return Response(json.dumps({"error": {"code": status, "mess": message, "details": {"message": message, "keys": ["none"]}}}), status=status, content_type="application/json", headers=NO_CACHE_HEADERS)

# ---------------
# Entry point
# ---------------

def run(port: int = 8080, debug: bool = False):
    app.logger.info("Server started!%s\n", " (debug mode)" if debug else "")
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False)
