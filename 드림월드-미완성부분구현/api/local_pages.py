"""Local status/help pages usable without Flash."""
from flask import Blueprint, Response, jsonify, render_template_string, request, redirect
from utils import save_data
from game_sync_server.entralinked.utility.db_manager import db

local = Blueprint("local", __name__, url_prefix="/local")


@local.route("/customize", methods=["GET", "POST"])
def customize():
    from api.customization import options, current, select
    if request.method == "POST":
        select(request.form)
        return redirect("/local/customize?saved=1", code=303)
    return render_template_string('''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>드림월드 커스터마이즈</title>
<style>body{font:17px/1.8 system-ui;background:#eef6fa;color:#243b48}main{max-width:760px;margin:35px auto;background:white;padding:32px;border-radius:16px}label{display:block;margin:20px 0}select{width:100%;padding:10px}button{padding:10px 24px}</style>
<main><h1>드림월드 커스터마이즈</h1><a href="/local/">이용 안내로 돌아가기</a>
<p>복구된 로컬 선택 화면입니다. 설치된 콘텐츠를 선택하면 게임싱크 전송 예약에 저장합니다. 포켓몬을 재운 다음 선택하고, 정상 종료 후 깨우세요.</p>
{% if saved %}<p role="status">선택을 저장했습니다. 다음 게임싱크 다운로드에 반영됩니다.</p>{% endif %}
<form method="post">{% for key, label in labels.items() %}<label>{{label}}<select name="{{key}}"><option value="">변경하지 않음</option>{% for name in choices[key] %}<option value="{{name}}" {% if selected[key]==name %}selected{% endif %}>{{name}}</option>{% endfor %}</select></label>{% endfor %}<button type="submit">전송 예약 저장</button></form></main></html>''', choices=options(), selected=current(), labels={"cgear":"C기어 스킨", "pokedex":"도감 스킨", "musical":"뮤지컬"}, saved=request.args.get("saved") == "1")


def status():
    member = save_data.read_player_data().get("member", {})
    sleeper = db.read(save_data.gscd, "sleeping_pokemon")
    state = save_data.read_entralink_data()
    return {
        "registered": bool(member),
        "sleeping": bool(sleeper) and member.get("play_status") in (1, 2, 3),
        "play_status": member.get("play_status", 0),
        "friend_board_count": len(state.get("friend_board", [])),
        "selected_pokemon_count": len(state.get("encounters", [])),
        "shelf_count": len(state.get("share_shelf", [])),
    }


@local.get("/status")
def get_status():
    return jsonify(status())


@local.get("/")
@local.get("/help")
def help_page():
    return render_template_string('''<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>드림월드 이용 안내</title>
<style>body{font:17px/1.8 system-ui,sans-serif;background:#eef6fa;color:#243b48;margin:0}main{max-width:820px;margin:36px auto;padding:32px;background:white;border-radius:18px}a{color:#166a91}nav{display:flex;gap:20px;flex-wrap:wrap}h1{font-size:28px}code{background:#edf3f5;padding:4px}li{margin-bottom:10px}.status{padding:18px;background:#e8f6ec;border-radius:8px}</style>
<main><h1>드림월드 이용 안내</h1><nav><a href="/">PGL 홈</a><a href="/pdw/">드림월드</a><a href="/profile/">마이페이지</a><a href="/local/customize">커스터마이즈</a><a href="/support/">보관된 도움말</a></nav>
<p class="status">현재 상태: {% if not s.registered %}게임싱크 계정을 먼저 등록하세요.{% elif s.sleeping %}포켓몬이 잠들어 있습니다. 드림월드에 입장할 수 있습니다.{% else %}포켓몬이 깨어 있습니다. 게임에서 먼저 포켓몬을 재우세요.{% endif %}</p>
<ol><li>서버 실행창을 열어 둔 채 게임의 C기어 → 온라인 → 게임싱크에서 포켓몬을 재웁니다.</li>
<li>Flash가 실행되는 Basilisk에서 <a href="/pdw/">드림월드</a>를 엽니다. Chrome·Edge는 원본 Flash 게임을 실행하지 못합니다. 독립 Flash Player에서는 <a href="/src/swf/theme/assets/common/main.swf">main.swf</a>를 열 수 있습니다.</li>
<li>집 밖으로 나와 무지개다리를 누르면 꿈섬에 갈 수 있습니다. 흔들리는 물체에서 미니게임을 완료하세요.</li>
<li>소원나무에 열매를 제공해 포켓몬을 친구보드에 등록하고, 집 안의 친구보드에서 보낼 포켓몬을 선택합니다.</li>
<li>이용을 마치면 드림월드에서 정상 종료한 뒤 게임싱크로 깨웁니다. 선택한 포켓몬은 하일링크 숲에서 확인합니다.</li></ol>
<h2>저장된 진행</h2><p>친구보드 {{s.friend_board_count}}마리 · 전송 선택 {{s.selected_pokemon_count}}마리 · 나눔선반 {{s.shelf_count}}개</p>
<h2>복구 범위</h2><p>꿈섬·지원 미니게임·소원나무·친구보드·텃밭·나눔선반과 기본 집 카탈로그를 연결했습니다. 새 집의 실내는 기본 오두막 배경을 사용합니다. 일반 가구 전체, 카페의 숲, 비스트로·촛불 끄기의 원본 진입 자료는 아직 부족합니다.</p>
<p>이 서버는 로컬 드림월드 복구용입니다. 옛 공식 회원가입·인터넷 대회·다른 이용자와의 온라인 교류 서비스는 연결되어 있지 않습니다. 보관된 도움말 일부는 영어 또는 일본어로 표시됩니다.</p>
</main></html>''', s=status())


@local.get("/client.js")
def client_script():
    return Response('''(function(){
var flash=false;try{flash=!!(navigator.mimeTypes&&navigator.mimeTypes['application/x-shockwave-flash']);}catch(e){}
if(!flash){var box=document.createElement('div');box.style.cssText='position:relative;z-index:99999;padding:16px;background:#fff3cf;color:#253844;font:16px/1.6 sans-serif;text-align:center';box.innerHTML='원본 드림월드는 Flash 실행 환경이 필요합니다. <a href="/local/">입장 방법·현재 게임싱크 상태 확인</a>';document.body.insertBefore(box,document.body.firstChild);}
if(/^\/(report|wifi|campaign)\//.test(location.pathname)){var note=document.createElement('p');note.style.cssText='position:relative;z-index:99999;background:#fff3cf;color:#253844;padding:12px;text-align:center';note.innerHTML='보관된 PGL 화면입니다. 리포트의 예시 데이터와 옛 공식 대회·캠페인은 실제 온라인 서비스에 연결되지 않습니다. <a href="/local/">현재 이용 가능한 기능</a>';document.body.insertBefore(note,document.body.firstChild);}
}());''', content_type="application/javascript")
