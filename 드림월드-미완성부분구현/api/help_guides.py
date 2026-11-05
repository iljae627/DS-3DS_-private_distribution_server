"""누락된 원본 설명 그림을 대신하는, 출처가 명확한 로컬 사용 안내."""
from html import escape
import re
from flask import Blueprint, Response, abort
from api.archive import render

guides = Blueprint("guides", __name__, url_prefix="/local/guide")
TOPICS = {
    "start": ("게임싱크와 입장", ["서버 실행", "포켓몬 재우기", "Flash에서 입장", "집과 꿈섬 탐색"], ["PC와 게임을 같은 네트워크에 연결하고 start-server.ps1에 표시된 DNS를 게임에 설정합니다.", "게임의 C기어 → 온라인 → 게임싱크에서 포켓몬을 재웁니다. 깨어 있으면 웹에서 입장할 수 없습니다.", "Basilisk 등 Flash 실행 환경에서 /pdw/를 엽니다. Chrome·Edge에서는 원본 Flash 게임이 실행되지 않습니다.", "집 밖의 무지개다리를 선택해 꿈섬으로 이동합니다. 서버 실행창을 유지하세요."]),
    "island": ("꿈섬과 소원나무", ["무지개다리", "꿈섬 탐색", "미니게임", "열매로 소원 빌기"], ["집 밖에서 무지개다리를 선택하면 꿈섬 탐색을 시작합니다.", "화살표로 이동하며 흔들리는 물체를 확인합니다. 아이템이나 포켓몬을 만날 수 있습니다.", "지원되는 미니게임을 성공하면 해당 포켓몬과 친해집니다. 실패 결과에는 보상이 지급되지 않습니다.", "소원나무에서 열매를 제공해 포켓몬을 친구보드에 등록합니다. 집으로 돌아가 전송할 포켓몬을 선택해야 합니다."]),
    "delivery": ("친구보드와 하일링크 수령", ["친구보드 선택", "아이템 전송 예약", "정상 종료·깨우기", "하일링크 수령"], ["집 안 친구보드에서 게임에 보낼 포켓몬을 선택합니다. 만났다는 사실만으로 전송되지는 않습니다.", "보물상자에서 보낼 아이템을 예약합니다. 취소하면 예약한 수량을 돌려받습니다.", "드림월드에서 정상 종료한 뒤 게임싱크로 포켓몬을 깨웁니다. 전송 도중 서버를 종료하지 마세요.", "게임의 C기어 → 무선통신 → 하일링크에서 숲의 포켓몬과 아이템을 확인합니다. 웹 테스트만으로 실기 수령이 보장되지는 않습니다."]),
    "garden": ("텃밭에서 열매 기르기", ["열매 준비", "빈 밭에 심기", "물주기·성장", "익은 열매 수확"], ["보물상자에 심을 열매가 있는지 확인합니다. 심을 때 열매 1개를 소비합니다.", "빈 칸에 열매를 심습니다. 이미 심은 칸에 겹쳐 심을 수 없습니다.", "물주기를 하고 성장 시간을 기다립니다. 페이지를 다시 열면 오프라인 경과 시간도 계산합니다.", "다 자란 열매만 수확할 수 있습니다. 꿈 포인트에 따른 밭 확장 시 기존 작물을 유지합니다."]),
    "room": ("집·카탈로그·나눔선반", ["보물상자 확인", "집 구매·변경", "방 배치 저장", "선반 전시·회수"], ["보물상자에서 열매와 아이템 수량을 확인합니다.", "카탈로그에 구현된 집을 열매로 구매하고 변경합니다. 일부 집의 실내는 기본 오두막 배경을 사용합니다.", "실제로 보유한 장식과 기본 보물상자·친구보드를 배치한 뒤 저장합니다. 원본 일반 가구 전체가 복원된 것은 아닙니다.", "나눔선반은 세 칸에 아이템을 전시하거나 회수할 수 있습니다. 실제 다른 이용자 서버와의 교환 서비스는 연결되어 있지 않습니다."]),
    "customize": ("스킨·도감·뮤지컬 전송", ["로컬 선택 화면", "설치 콘텐츠 선택", "전송 예약 저장", "게임싱크 수령"], ["상단 커스터마이즈 링크 또는 /local/customize를 엽니다.", "현재 게임 버전에 맞게 실제 설치된 C기어 스킨·도감 스킨·뮤지컬 목록을 표시합니다.", "원하는 항목을 선택해 전송 예약을 저장합니다. 목록에 없는 파일명은 사용할 수 없습니다.", "포켓몬을 재운 상태에서 선택하고 정상 종료 후 깨워 게임싱크 다운로드를 진행합니다. 공식 캠페인 접수는 제공하지 않습니다."]),
    "archive": ("보관 페이지와 로컬 지원 범위", ["페이지 목록", "원본 이미지 자료실", "로컬 기능 확인", "원본·재구성 구분"], ["전체 페이지 목록에서 보관된 도움말과 링크를 찾아볼 수 있습니다. 일부는 영어·일본어입니다.", "이미지 자료실에서는 실제 남아 있는 이미지의 원본 크기와 파일 경로를 확인합니다. 작은 임시 이미지는 제외합니다.", "계정 상태·커스터마이즈는 로컬 안내에서 확인합니다. 옛 공식 회원가입·대회·온라인 친구 서비스는 운영하지 않습니다.", "이 설명도는 현재 로컬 서버를 위한 재구성 자료입니다. 누락된 원본 스크린샷을 복원한 이미지가 아닙니다."]),
}


def topic_for(path):
    if "/custom/" in path or "/customize" in path:
        return "customize"
    match = re.search(r"/world/(\d+)", path)
    if match:
        number = int(match[1])
        if number in (803, 804, 811, 812):
            return "delivery"
        if 814 <= number <= 816:
            return "garden"
        if number in (810, 813, 817):
            return "room"
        if number in (821, 822, 823):
            return "island"
        return "start"
    match = re.search(r"/help/(\d+)", path)
    if match:
        number = int(match[1])
        if 430 <= number <= 435:
            return "garden"
        if number in (404, 405, 424):
            return "delivery"
        if 450 <= number <= 461:
            return "island"
        if 410 <= number <= 443:
            return "room"
    if "/cooperation/" in path:
        return "start"
    return "archive"


@guides.get("/<topic>.svg")
def illustration(topic):
    if topic not in TOPICS:
        abort(404)
    title, steps, _ = TOPICS[topic]
    cards = []
    for i, label in enumerate(steps):
        y = 95 + i * 72
        cards.append(f'<rect x="24" y="{y}" width="552" height="56" rx="12" fill="#edf6fa"/><circle cx="55" cy="{y+28}" r="18" fill="#24779b"/><text x="55" y="{y+35}" text-anchor="middle" fill="white" font-size="19">{i+1}</text><text x="88" y="{y+35}" fill="#243b48" font-size="20">{escape(label)}</text>')
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="418" viewBox="0 0 600 418" role="img"><title>{escape(title)} — 로컬 사용 순서 재구성</title><rect width="600" height="418" rx="16" fill="white"/><g font-family="sans-serif"><text x="24" y="37" font-size="23" fill="#243b48">{escape(title)}</text><text x="24" y="67" font-size="14" fill="#6a5140">로컬 사용 안내 · 누락된 원본 스크린샷의 복구본이 아닙니다</text>{"".join(cards)}<text x="24" y="402" font-size="14" fill="#526775">클릭하면 단계별 사용 방법과 지원 범위를 확인할 수 있습니다.</text></g></svg>'
    return Response(svg, content_type="image/svg+xml", headers={"X-PDW-Reconstructed": "local-guide-not-original"})


@guides.get("/<topic>")
def guide(topic):
    if topic not in TOPICS:
        abort(404)
    title, steps, notes = TOPICS[topic]
    return render('''<h1>{{title}}</h1><p class="note">현재 로컬 서버를 위한 재구성 안내입니다. 아래 설명도는 원본 스크린샷이 아닙니다.</p><img class="detail" src="/local/guide/{{topic}}.svg" alt="{{title}} 순서"><ol>{% for note in notes %}<li>{{note}}</li>{% endfor %}</ol><h2>다른 사용 방법</h2><ul>{% for key, value in topics.items() %}<li><a href="/local/guide/{{key}}">{{value[0]}}</a></li>{% endfor %}</ul>''', title=title, topic=topic, notes=notes, topics=TOPICS)
