# 포켓몬 배포 파일 변환 도구와 3DS 사설 배포 서버

서비스가 종료된 Nintendo DS·3DS 포켓몬 배포 기능을 개인 환경에서 분석하고 재현하는 프로젝트다. 포켓몬 개체 파일을 Wonder Card로 변환하는 도구와 게임의 배포 요청에 응답하는 사설 서버를 함께 개발한다.

현재 Nintendo DS 4세대에서는 `PK4 → PCD → MYG → 실기 수령` 흐름을 확인했다. 5세대는 PK5·PGF 변환과 DLS 서버를 구현했으며, 6세대는 WC6 목록과 NPFL/NPDL 경로를 구현했지만 실기 배포에 필요한 Nintendo 서명 BOSS 컨테이너와 인증 조건이 남아 있다.

> 개인 소유 게임과 로컬 네트워크에서의 연구·보존·호환성 시험을 위한 프로젝트다. Nintendo의 공식 서비스가 아니며 ROM, 세이브, 개인 키, 공식 인증서와 타인의 자격 증명을 제공하지 않는다.

## 현재 상태

| 구성요소 | 구현 내용 | 검증 상태 |
|---|---|---|
| 4세대 배포 서버 | 선택적 DNS, DS용 SSLv3/TLSv1, DLS `count → list → contents`, PCD→MYG | 실제 DS 배포·수령 확인 |
| 4세대 변환기 | 136/236바이트 PK4를 856바이트 PCD로 변환 | 생성 PCD의 실제 수령 확인 |
| 5세대 배포 서버 | 204바이트 PGF를 720바이트 WC5FULL 응답으로 구성 | 자동 테스트 구현, 환경별 실기 검증 필요 |
| 5세대 변환기 | 136/220바이트 PK5를 204바이트 PGF로 변환 | 출력 재검증과 자체 테스트 구현 |
| 6세대 배포 서버 | WC6 검사·선택, NPFL 목록, NPDL 다운로드 경로 | 개발용 서버 구현, 일반 실기 배포 미완성 |
| 드림월드 기준본 | Game Sync와 웹 서버 실행 환경 및 업스트림 구현 기능 | 실행 절차 정리, 일부 기능 미구현 |
| 드림월드 실험본 | 친구보드·Entralink·카탈로그·나눔선반 보완 | 자동 테스트 구현, 원본 자산 누락 항목 존재 |

## 지금까지 진행한 작업

### 1. 4세대 통신과 배포 서버 분석

- Windows 모바일 핫스팟을 이용해 DS와 PC를 연결했다.
- Windows ICS가 사용하는 DNS와 로컬 서버의 53번 포트 충돌을 분석했다.
- WinDivert로 핫스팟에서 들어오는 Nintendo/WFC DNS 패킷만 선택적으로 처리했다.
- 연결 시험과 DLS 도메인은 로컬 서버로, NAS 인증 요청은 호환 가능한 외부 경로로 분리했다.
- DS가 사용하는 SSLv3/TLSv1 요청을 받을 수 있는 HTTPS 계층을 구성했다.
- Nintendo DLS의 `count`, `list`, `contents` 요청과 936바이트 MYG 응답을 구현했다.
- DNS, TCP, TLS, HTTP와 DLS 단계를 구분하는 진단 로그를 추가했다.
- 방화벽 전체 해제 대신 TCP 80·443 인바운드 규칙만 사용하도록 정리했다.

### 2. PK4·PCD·MYG 구조 분석과 변환기 개발

- PK4의 136바이트 박스 형식과 236바이트 파티 형식을 구분했다.
- PID, 체크섬, LCRNG XOR 암호화와 네 개 데이터 블록의 순서 변환을 분석했다.
- 정상 PCD를 비교하여 선물 데이터, 카드 ID, 게임 비트마스크, 설명문과 재배포 필드를 확인했다.
- `MYG = PCD[0x104:0x154] + PCD` 관계를 서버 변환에 적용했다.
- 초기 템플릿 교체 실험을 거쳐 독립적인 PCD 객체를 생성하는 변환기로 개선했다.
- PK4 크기·종 번호·체크섬을 검사하고 저장 후 PCD를 다시 읽어 종 번호와 크기를 검증한다.
- 같은 PK4에서 같은 카드 ID가 나오도록 SHA-256 기반 기본 ID 생성 규칙을 추가했다.

### 3. 5세대 확장

- 5세대 DLS가 사용하는 PGF와 720바이트 전송 구조를 구현했다.
- 언어·게임 수신 플래그, 안내문과 CRC16-CCITT를 포함하도록 서버를 구성했다.
- PK5를 PGF 선물 템플릿으로 변환하는 도구를 추가했다.
- PGF에 저장할 수 없는 경험치, 노력치와 현재 HP 등의 제한을 문서화했다.

### 4. 3DS 6세대 선행 구현

- 264바이트 WC6 파일의 크기와 카드 ID를 검사한다.
- NPFL 파일 목록과 NPDL 다운로드 경로를 구현했다.
- WC6 원본과 Nintendo가 서명·암호화한 BOSS 컨테이너를 구분했다.
- 인증서 고정, 클라이언트 인증, BOSS AES-CTR 및 서명 문제 때문에 일반 WC6만으로 실기 배포할 수 없음을 확인했다.

### 5. 포켓몬 드림월드 보존 실험

- 공개된 Dream World Reawakened 구현을 기반으로 Game Sync와 웹 서버 실행 절차를 정리했다.
- `드림월드` 폴더는 업스트림에 가까운 기준본으로 유지한다.
- `드림월드-미완성부분구현` 폴더에는 소원의 나무, Friend Board, Entralink 전송, Dream Catalogue와 Share Shelf 상태 처리 실험이 포함되어 있다.
- 일부 미니게임은 원본 SWF와 캠페인 메타데이터가 없어 완전한 복원이 어렵다.

## 폴더 구성

```text
4세대-배포/                  4세대 DNS·HTTP·HTTPS·DLS 서버
4세대-배포파일-변환기/      PK4 → PCD 변환기
5세대-배포서버/             5세대 PGF 배포 서버
5세대-배포파일-변환기/      PK5 → PGF 변환기
6세대-배포서버/             WC6·NPFL·NPDL 선행 구현
드림월드/                    업스트림에 가까운 실행 기준본
드림월드-미완성부분구현/    추가 기능을 적용한 비교·실험본
프로젝트_보고서_gitignore/  Git에서 제외한 로컬 보고서·시험 자료
```

## 4세대 빠른 시작

### 준비물

- Windows 10/11 PC와 인터넷 연결
- DS가 연결할 수 있는 2.4GHz 무선 네트워크
- 포켓몬스터 디아루가·펄기아·플라티나·하트골드·소울실버 중 하나
- 856바이트 `.pcd` 파일 또는 변환할 `.pk4`

4세대 DS 게임은 최신 WPA2/WPA3 핫스팟에 연결하지 못할 수 있다. 필요하면 시험용 2.4GHz Open 네트워크나 별도 호환 AP를 사용한다. Windows Defender 방화벽 전체를 끌 필요는 없다.

### 1. PK4를 PCD로 변환

1. PKHeX에서 배포할 포켓몬을 `.pk4`로 내보낸다.
2. PK4를 `4세대-배포파일-변환기\PK4를 PCD로 변환.cmd` 위로 끌어다 놓는다.
3. 같은 폴더에 856바이트 `.pcd`가 생성됐는지 확인한다.
4. 생성된 파일을 `4세대-배포\배포 목록\`에 복사한다.

변환 옵션과 오류 해결은 [4세대 변환기 README](4세대-배포파일-변환기/README.md)를 참고한다.

### 2. 배포 서버 실행

먼저 Windows 모바일 핫스팟을 켠다. 이후 `4세대-배포` 폴더에서 **관리자 권한 PowerShell**을 열고 실행한다.

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\start-server.ps1
```

핫스팟 주소가 기본값과 다르면 실제 주소를 지정한다.

```powershell
.\start-server.ps1 -HotspotIp 192.168.137.1
```

README에 적힌 주소를 그대로 입력하지 말고 서버 시작 화면에 표시된 `DS 기본/보조 DNS` 주소를 사용한다.

정상 시작 로그 예시는 다음과 같다.

```text
[BOOT-HTTP] listening=<핫스팟 주소>:80
[BOOT-HTTPS] listening=<핫스팟 주소>:443 protocols=SSLv3,TLSv1
[SELFTEST-HTTP-PASS]
[SELFTEST-DNS-PASS] WinDivert driver opened
```

### 3. DS에서 수령

1. 게임의 `Nintendo Wi-Fi Connection 설정`을 연다.
2. PC에서 만든 2.4GHz 호환 네트워크에 연결한다.
3. IP 주소 자동 취득은 `예`로 둔다.
4. DNS 자동 취득을 `아니오`로 바꾼다.
5. 기본 DNS와 보조 DNS에 서버가 표시한 핫스팟 주소를 입력한다.
6. 연결 시험 후 `이상한 소포 → 소포를 받는다 → Nintendo WFC로 받는다`를 선택한다.

수령 과정에서는 다음 로그가 순서대로 나타난다.

```text
[NDS-DNS-01] captured-direct
[NDS-DNS-02] spoofed-direct
[NDS-TLS-02] handshake-complete
[NDS-GIFT-SELECT] selected=private-gift-001.myg
[NDS-DLS-01] request action=count
[NDS-DLS-01] request action=list
[NDS-DLS-01] request action=contents
[NDS-DLS-02] response action=contents status=200 bytes=936
```

종료는 PowerShell에서 `Ctrl+C`를 누른다. 자세한 진단 방법은 [4세대 서버 README](4세대-배포/README.md)를 참고한다.

## 5세대 사용법

### PK5를 PGF로 변환

1. PKHeX에서 포켓몬을 136바이트 또는 220바이트 `.pk5`로 내보낸다.
2. PK5를 `5세대-배포파일-변환기\PK5를 PGF로 변환.cmd` 위로 끌어다 놓는다.
3. 생성된 204바이트 `.pgf`를 `5세대-배포서버\배포파일\`에 복사한다.

자세한 옵션과 변환되지 않는 PK5 상태 정보는 [5세대 변환기 README](5세대-배포파일-변환기/README.md)를 참고한다.

### 서버 실행

5세대 서버는 4세대 서버의 Windows 핫스팟과 Python 환경 및 인증서 준비를 공유한다. `5세대-배포서버` 폴더에서 관리자 PowerShell을 열고 실행한다.

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\start-server.ps1
```

DS의 기본·보조 DNS를 화면에 표시된 주소로 설정하고 블랙·화이트·블랙2·화이트2의 이상한 소포에서 Nintendo WFC 수령을 선택한다. 세부 내용은 [5세대 서버 README](5세대-배포서버/README.md)를 참고한다.

## 6세대 개발 서버

6세대 폴더의 서버는 WC6 검사와 NPFL/NPDL 요청 연구용이다.

```powershell
cd .\6세대-배포서버
Set-ExecutionPolicy -Scope Process Bypass
.\start-server.ps1
```

기본 확인 주소는 다음과 같다.

- `/health`: 서버 상태
- `/api/gift`: 현재 선택한 WC6 원본
- `/p01/filelist/<appId>/<taskId>`: NPFL 목록
- `/p01/nsa/<appId>/<taskId>/<파일명>`: NPDL 다운로드

이 서버만으로 일반 3DS 실기에서 임의 WC6를 받을 수는 없다. 서명·암호화된 `.boss`, 올바른 앱·태스크 ID, DNS·HTTPS 라우팅과 클라이언트 인증 조건이 별도로 필요하다. 자세한 제한은 [6세대 서버 README](6세대-배포서버/README.md)를 확인한다.

## 드림월드 실행

`드림월드`와 `드림월드-미완성부분구현`은 각각 별도의 Python 가상환경을 사용한다. 기준 동작을 확인하려면 `드림월드`, 추가 복원 기능을 시험하려면 `드림월드-미완성부분구현`에서 다음 명령을 사용한다.

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\start-server.ps1
```

스크립트는 `.venv`를 만들고 의존성을 설치한 뒤 환경 진단과 서버 실행을 진행한다. 웹 콘텐츠는 오래된 Flash 환경에 의존하며 Ruffle에서 완전히 동작하지 않는다. 외부에서 받은 브라우저나 Flash 실행 파일을 사용할 때는 격리된 시험 환경을 권장한다.

## 자동 테스트

각 서버 폴더에서 해당 테스트를 실행한다.

```powershell
# 4세대
Push-Location .\4세대-배포
.\.venv\Scripts\python.exe -m unittest -v test_server.py
Pop-Location

# 5세대
Push-Location .\5세대-배포서버
..\4세대-배포\.venv\Scripts\python.exe -m unittest -v test_server.py
Pop-Location

# 6세대
Push-Location .\6세대-배포서버
python -m unittest -v test_server.py
Pop-Location

# 드림월드
Push-Location .\드림월드
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Pop-Location
```

변환기 자체 검사는 다음과 같이 실행할 수 있다.

```powershell
dotnet ".\5세대-배포파일-변환기\Gen5Converter.dll" --self-test
```

## 문제 해결

### 서버 시작 전에 핫스팟 주소 오류가 발생함

모바일 핫스팟을 먼저 켠 뒤 서버를 실행한다. 주소가 `192.168.137.1`이 아니면 `-HotspotIp` 옵션에 실제 핫스팟 IPv4를 지정한다.

### `SELFTEST-DNS-FAIL`

관리자 권한, WinDivert 드라이버 로딩, 보안 프로그램의 드라이버 차단 여부를 확인한다.

### DS 연결 시험부터 실패함

2.4GHz·802.11b/g 호환 여부와 무선 암호화 방식을 확인한다. DS의 DNS에는 상위 인터넷 연결 주소가 아니라 PC 모바일 핫스팟 쪽 주소를 입력해야 한다.

### DNS 로그는 있지만 DLS 요청이 없음

`NDS-TCP-01`, `NDS-HTTP-01`, `NDS-TLS-02` 순서에서 마지막으로 기록된 단계를 확인한다. 인터넷 연결 또는 외부 WFC 인증 경로 문제일 수도 있다.

### 선물을 전송했지만 게임에서 받을 수 없음

- Wonder Card 보관 공간이 남아 있는지 확인한다.
- 같은 Card ID의 카드나 수령 기록을 삭제한다.
- 현재 게임이 카드의 호환 게임 플래그에 포함되는지 확인한다.
- 기존 검증 완료 PCD로 네트워크 문제와 생성 파일 문제를 구분한다.
- 원본 세이브를 먼저 백업한다.

## 보안과 자료 관리

- 서버는 로컬 네트워크 시험을 전제로 하며 공유기 포트 포워딩을 요구하지 않는다.
- Windows Defender 방화벽 전체를 끄지 않고 필요한 포트만 허용한다.
- Nintendo/WFC 관련 DNS만 처리하고 일반 DNS 패킷은 Windows ICS에 돌려준다.
- 인증서 개인 키, ROM, 세이브와 민감한 패킷 로그는 Git에 올리지 않는다.
- `프로젝트_보고서_gitignore` 폴더는 `.gitignore`에서 제외한다.
- 배포 파일과 변환 결과는 공식 이벤트로 오인되지 않도록 별도로 관리한다.

## 알려진 제한

- 4세대 실기 성공은 확인했지만 모든 언어·게임·포켓몬 조합을 보장하지 않는다.
- 5세대는 파일 구조와 서버 자동 테스트를 구현했으며 환경별 실기 검증이 더 필요하다.
- 6세대는 Nintendo 서명 BOSS 컨테이너와 인증 조건 없이는 임의 WC6를 실기에 배포할 수 없다.
- 변환기는 포켓몬 파일의 구조적 유효성을 검사하지만 PKHeX의 적법성 검사를 대신하지 않는다.
- 외부 WFC 호환 서비스가 중단되거나 주소가 변경되면 인증 단계가 실패할 수 있다.
- 드림월드는 누락된 원본 Flash 자산 때문에 일부 기능을 완전히 복원할 수 없다.

## 참고 구현

- [PKHeX](https://github.com/kwsch/PKHeX)
- [dwc network server emulator](https://github.com/barronwaffles/dwc_network_server_emulator)
- [nds constraint](https://github.com/KaeruTeam/nds-constraint)
- [IVgift](https://github.com/vixthevix/IVgift)
- [Dream World Reawakened](https://github.com/minibug1021/dreamworld-reawakened)

외부 프로젝트의 코드와 자료는 각 라이선스와 사용 조건을 따른다.
