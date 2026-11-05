"""원본 이미지·페이지 탐색. 원본이 없는 자료를 복구한 것처럼 표시하지 않는다."""
from functools import lru_cache
import hashlib
from pathlib import Path
import re
from urllib.parse import quote
from flask import Blueprint, Response, abort, render_template_string, request, send_file

archive = Blueprint("archive", __name__, url_prefix="/local")
ASSETS = Path(__file__).resolve().parents[1] / "dreamworld_assets"
LANGUAGES = ("ko", "en", "ja", "de", "fr", "it", "es", "shared")
STYLE = '''body{font:16px/1.7 system-ui,sans-serif;color:#243b48;background:#eef6fa;margin:0}main{max-width:1120px;margin:25px auto;padding:25px;background:white;border-radius:16px}nav{display:flex;flex-wrap:wrap;gap:18px;margin:16px 0}a{color:#12618b}input,select,button{font:inherit;padding:8px;max-width:100%}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:16px}.card{border:1px solid #cbd9de;border-radius:12px;padding:14px;overflow-wrap:anywhere}.card img{width:100%;height:165px;object-fit:contain;background:#f1f5f6}.detail{display:block;max-width:100%;height:auto;margin:24px auto;background:#f1f5f6}code{overflow-wrap:anywhere}li{margin:9px 0}.note{background:#fff3cf;padding:14px}h1{font-size:28px}'''
HEAD = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ title }}</title><style>{{ style }}</style><main><nav><a href="/local/">이용 안내</a><a href="/local/pages">전체 페이지</a><a href="/local/gallery">원본 이미지 자료실</a><a href="/local/customize">커스터마이즈</a><a href="/pdw/">드림월드</a></nav>'''


@lru_cache(maxsize=1)
def inventory():
    images, pages = {}, {}
    for lang in LANGUAGES:
        root = ASSETS / (lang + ".pokemon-gl.com")
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif") and path.stat().st_size > 100:
                key = hashlib.sha256(path.relative_to(ASSETS).as_posix().encode()).hexdigest()[:20]
                images[key] = {"id": key, "file": path, "path": relative, "language": lang}
            elif path.suffix.lower() == ".html" and lang != "shared":
                pages.setdefault(relative, []).append(lang)
    return images, pages


def render(body, **values):
    return render_template_string(HEAD + body + "</main></html>", style=STYLE, **values)


@archive.get("/gallery")
def gallery():
    query = request.args.get("q", "").strip().lower()[:150]
    lang = request.args.get("lang", "")
    try:
        page = max(1, int(request.args.get("page", "1")))
    except ValueError:
        abort(400)
    rows = [v for v in inventory()[0].values() if query in v["path"].lower() and (not lang or lang == v["language"])]
    total = len(rows)
    maximum = max(1, (total + 39) // 40)
    page = min(page, maximum)
    return render('''<h1>원본 이미지 자료실</h1><p>보관된 원본 이미지를 클릭하면 상세 화면에서 원래 해상도로 확인할 수 있습니다. 100바이트 이하 임시 이미지는 목록에서 제외했습니다. 권리는 원 권리자에게 있습니다.</p><form><input name="q" aria-label="이미지 경로 검색" value="{{q}}" placeholder="support/help 또는 이미지 이름"><select name="lang" aria-label="자료 언어"><option value="">전체 언어</option>{% for code in languages %}<option value="{{code}}" {% if code==lang %}selected{% endif %}>{{code}}</option>{% endfor %}</select><button>검색</button></form><p>{{total}}개 · {{page}} / {{maximum}} 페이지</p><div class="grid">{% for row in rows %}<a class="card" href="/local/gallery/{{row.id}}"><img loading="lazy" src="/local/image/{{row.id}}" alt="{{row.path}}"><p>{{row.language}} · {{row.path}}</p></a>{% else %}<p>일치하는 원본 이미지가 없습니다.</p>{% endfor %}</div><nav>{% if page>1 %}<a href="{{url_for('archive.gallery',q=q,lang=lang,page=page-1)}}">이전</a>{% endif %}{% if page<maximum %}<a href="{{url_for('archive.gallery',q=q,lang=lang,page=page+1)}}">다음</a>{% endif %}</nav>''', title="드림월드 원본 이미지 자료실", rows=rows[(page-1)*40:page*40], total=total, page=page, maximum=maximum, q=query, lang=lang, languages=LANGUAGES)


@archive.get("/gallery/<key>")
def detail(key):
    row = inventory()[0].get(key)
    if row is None:
        abort(404)
    return render('''<h1>이미지 상세 보기</h1><p><a href="{{url_for('archive.gallery',lang=row.language)}}">{{row.language}} 자료 목록</a> · <a href="/local/image/{{row.id}}">원래 해상도로 열기</a></p><code>{{row.language}}.pokemon-gl.com/{{row.path}}</code><a href="/local/image/{{row.id}}"><img class="detail" src="/local/image/{{row.id}}" alt="{{row.path}}"></a><p>원본 파일 크기: {{size}}바이트</p>''', title="드림월드 이미지 상세", row=row, size=row["file"].stat().st_size)


@archive.get("/image/<key>")
def image(key):
    row = inventory()[0].get(key)
    if row is None:
        abort(404)
    return send_file(row["file"], conditional=True)


@archive.get("/pages")
def pages():
    query = request.args.get("q", "").strip().lower()[:150]
    rows = [(path, langs) for path, langs in sorted(inventory()[1].items()) if query in path.lower()]
    return render('''<h1>보관 페이지 목록</h1><p>원본 페이지 경로와 보관된 언어를 표시합니다. 기본 링크는 현재 계정 언어를 우선 사용하며, 없는 경우 보관된 언어로 표시됩니다. 옛 공식 회원가입·대회 등은 실제 서비스가 아닙니다.</p><form><input aria-label="페이지 경로 검색" name="q" value="{{q}}" placeholder="support/help/world"><button>검색</button></form><p>{{rows|length}}개 경로</p><ul>{% for path, langs in rows %}<li><a href="/{{path}}">/{{path}}</a> <small>{{langs|join(', ')}}</small></li>{% endfor %}</ul>''', title="드림월드 전체 페이지", q=query, rows=rows)


@archive.get("/archive.css")
def archive_css():
    return Response('''#help-content{font:16px/1.7 system-ui;background:white;padding:22px;color:#253844;overflow:auto}#help-menu,#help-sub-menu{float:left;width:210px;margin:0 24px 18px 0}#help-menu{display:flex;flex-wrap:wrap;gap:6px;float:none;width:auto}#help-body{margin-left:235px}#help-content a{color:#145c83;text-decoration:underline}#help-content img{max-width:100%;height:auto}#help-menu a{padding:7px;background:#edf5f8}#help-menu a:empty:after{content:attr(id)}#help-content h2,#help-content h3{font-size:20px;margin:15px 0}#help-sub-menu ol{padding-left:18px}.supprot_gNavi ul{display:flex;flex-wrap:wrap;gap:8px}.supprot_gNavi ul ul{position:static!important}.supprot_gNavi li{height:auto!important;line-height:1.6!important}#pdw-local-nav{position:relative;z-index:10000;background:#eef6fa;padding:10px;text-align:center;font:15px/1.8 system-ui}#pdw-local-nav a{color:#145c83;margin:0 10px}.pdw-image-dialog{max-width:94vw;max-height:94vh;border:1px solid #aab9bf;border-radius:12px;padding:16px}.pdw-image-dialog img{display:block;max-width:86vw;max-height:78vh;object-fit:contain}.pdw-image-dialog::backdrop{background:#0009}''', content_type="text/css")


@archive.get("/legacy.css")
def legacy_css():
    return Response('''/* 누락된 초기 사이트 스타일을 대신하는 로컬 읽기용 스타일 */
body{font:16px/1.8 system-ui,sans-serif;color:#253844;background:#eef6fa;margin:0}#wrapper,.MainCont,#container{max-width:1040px;margin:auto;background:white;padding:24px;box-sizing:border-box}img{max-width:100%;height:auto}a{color:#145c83}table{max-width:100%;border-collapse:collapse}td,th{padding:8px}h1,h2,h3{line-height:1.5}''', content_type="text/css")


@archive.get("/legacy.js")
def legacy_js():
    return Response('''/* 원본 복원이 아닌 로컬 아카이브 UI 보완 */
(function(){if(document.getElementById('pdw-legacy-style'))return;var s=document.createElement('link');s.id='pdw-legacy-style';s.rel='stylesheet';s.href='/local/legacy.css';document.head.appendChild(s);document.addEventListener('DOMContentLoaded',function(){var n=document.createElement('p');n.textContent='이 화면은 초기 공식 사이트 보관본입니다. 회원가입·문의 접수 등 외부 서비스는 제공하지 않습니다.';n.style.cssText='padding:12px;background:#fff3cf;color:#253844';document.body.insertBefore(n,document.body.firstChild);});}());''', content_type="application/javascript")
