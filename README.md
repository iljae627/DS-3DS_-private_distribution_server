# Nintendo DS / 3DS Pokémon 사설 배포 서버 개발

## 진행 상태

최종 목표는 원하는 PKM을 배포 파일로 변환하는 도구를 개발하고 3DS 사설 배포 서버를 구현하는 것입니다. 현재는 선행 단계인 DS 통신과 기존 정상 배포 파일의 실제 배포에 성공했습니다. PC 핫스팟과 보안 설정 해제에 의존하는 연결 환경은 개선 중이며, 원하는 PKM을 PCD·MYG로 변환하는 작업은 파일 구조 분석 및 검증 단계입니다. 아래 기능 목록은 구현된 코드의 범위를 설명하며, 모든 게임에서의 수령 성공이나 3DS 지원 완료를 의미하지 않습니다.

상세 진행 상황은 [9월 프로젝트 보고서](9월_프로젝트_보고서_초안.md)를 참고하세요.

ROM·세이브·배포 데이터·로그·인증서·개인 키·외부 참고 소스는 Git에 포함하지 않습니다. HTTPS 기능에 필요한 로컬 인증서와 키는 별도로 준비해야 합니다. `samples/reference/mew_reference.myg`가 없는 환경에서는 해당 로컬 파일을 사용하는 테스트 1개가 건너뛰어집니다.

로컬 네트워크에서 본인 소유의 Nintendo DS Pokémon 게임을 대상으로 다음 기능을 제공합니다.

- 4세대(D/P/Pt/HG/SS) GTS를 통한 `.pk4` Pokémon 전송
- 4세대 PKHeX `.pcd` → 936바이트 DLS 배포 파일 자동 변환
- 5세대(B/W/B2/W2) PKHeX `.pgf` → 720바이트 DLS 배포 파일 자동 변환
- DNS 선택 리디렉션과 Nintendo DLS `count → list → contents` 처리
- DNS/HTTP/DLS/GTS 요청 JSONL 기록, hex 덤프 및 Wireshark PCAP 분석
- 서버 PC에서만 접근 가능한 웹 관리 화면

이 저장소에는 ROM, 공식 이벤트 데이터, 인증서, 개인 키가 포함되어 있지 않습니다.

## 빠른 시작

요구 사항은 Python 3.11 이상뿐입니다. 현재 PC의 Python 3.14에서도 테스트됩니다.

1. PowerShell을 **관리자 권한**으로 엽니다.
2. 이 폴더에서 서버를 시작합니다.

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\start.ps1
```

3. 브라우저에서 `http://127.0.0.1/`을 엽니다.
4. PKHeX에서 만든 파일을 해당 칸에 올립니다.
5. 콘솔에 표시된 `DS 기본 DNS` 주소를 DS의 Primary DNS에 입력합니다.

Windows 방화벽이 묻는다면 **개인 네트워크**만 허용하는 것을 권장합니다. 인터넷 포트 포워딩은 하지 마세요.

### Windows 모바일 핫스팟 + 실기 DS

1. Windows `설정 → 네트워크 및 인터넷 → 모바일 핫스팟`에서 핫스팟을 켭니다.
2. 가능하면 2.4GHz 대역을 선택합니다. DS/DS Lite는 WPA2 핫스팟에 직접 연결하지 못할 수 있으므로, 실기에서는 무암호 2.4GHz 보조 AP 또는 호환 공유기가 필요할 수 있습니다.
3. 핫스팟이 켜진 뒤 서버를 시작합니다. `public_ip: auto`는 실제 `192.168.137.1` 인터페이스가 있을 때만 그 주소를 선택합니다.
4. DS 연결 설정에서 IP와 DNS 자동 취득을 끄지 말고, Primary DNS만 서버가 표시한 주소로 바꿉니다. Secondary DNS는 `0.0.0.0`으로 둡니다.
5. 방화벽 인바운드는 UDP 53과 TCP 80을 **개인 네트워크/로컬 서브넷**에만 허용합니다. 공유기 포트 포워딩은 사용하지 않습니다.

### melonDS 1.1 테스트 프로필

melonDS를 완전히 종료한 뒤 다음 명령을 실행하면 공식 melonDS 형식의 `wfcsettings.bin`을 생성합니다. 첫 프로필은 `melonAP`, DHCP 자동, Primary DNS는 현재 서버 PC 주소입니다.

```powershell
python .\configure_melonds_wfc.py --dns auto
```

melonDS에서는 `Config → Wifi settings → Indirect mode (uses libslirp)`를 선택합니다. ROM의 Wi-Fi 설정 메뉴에서 프로필을 다시 만들 필요 없이 생성된 파일을 읽습니다. 다른 melonDS 폴더도 함께 설정하려면 `--output C:\경로\wfcsettings.bin`을 반복 지정하세요. 기존 파일은 `.bak`으로 보존됩니다.

포트 53/80을 이미 다른 프로그램이 사용한다면 테스트용으로 다음처럼 실행할 수 있습니다. 실제 DS는 기본적으로 DLS HTTP 포트 80을 기대하므로 실기 연결에는 기본 포트가 권장됩니다.

```powershell
python server.py --dns-port 5353 --http-port 8080
```

## 게임별 사용법

### 4세대 GTS로 원하는 Pokémon 보내기

1. PKHeX에서 4세대 Pokémon을 `.pk4` 또는 `.pkm`으로 내보냅니다.
2. 관리 화면의 **4세대 GTS로 Pokémon 보내기**에 업로드합니다.
3. 게임에서 GTS에 입장합니다.
4. 활성 파일이 GTS 결과 패킷으로 전송됩니다.

236바이트 party PK4가 가장 안정적입니다. 136바이트 box PK4도 받을 수 있지만 서버가 최소 party 꼬리를 생성하므로, 수신 후 Pokémon Center에서 회복하거나 PC에 넣었다 꺼내 스탯을 다시 계산시키는 것을 권장합니다.

### 4세대 미스터리 기프트

1. PKHeX에서 `.pcd` Wonder Card를 준비합니다.
2. 관리 화면의 **4세대 미스터리 기프트**에 업로드합니다.
3. 게임에서 `Mystery Gift → Receive Gift → Get via Nintendo WFC`를 선택합니다.

서버는 PCD의 80바이트 다운로드 헤더를 앞으로 옮기고, Pokémon payload가 있으면 Gen-IV 방식으로 암호화하여 936바이트 `.myg`를 생성합니다.

### 5세대 미스터리 기프트

1. PKHeX에서 `.pgf`를 준비합니다. 연결 시험용 한국어 피카츄는 `samples/gen5_test_pikachu_ko.pgf`에 있습니다.
2. 언어와 허용 버전을 고르고 업로드합니다.
3. 게임에서 `Mystery Gift → Receive Gift → Get via Nintendo WFC`를 선택합니다.

지원 언어 코드는 `k/e/j/f/g/i/s`, 버전 문자열은 `w`, `b`, `w2`, `b2`의 조합입니다. 예: `bw`, `b2w2`, `wbw2b2`.

## WFC/HTTPS 제한

Nintendo WFC는 종료되었고 DS 게임은 원래의 NAS 인증 및 일부 HTTPS 경로를 사용합니다. 이 프로그램은 로컬 배포/DNS 계층과 DS용 SSLv3/443 호환 계층을 구현합니다. 포함된 인증서는 로컬 시험용이며 Nintendo 인증서를 사칭하지 않습니다.

- GTS HTTP 경로는 로컬 DNS 리디렉션으로 동작할 수 있습니다.
- `config.json`의 `enable_legacy_https`가 `true`이면 `tlslite-ng`로 443/SSLv3 요청을 받아 같은 서버의 `/download`로 전달합니다.
- `31020`과 함께 DNS 로그만 있고 HTTP 로그가 없다면 `ssl3_connect`/`ssl3_error`를 확인하세요. `ssl3_connect`도 없으면 방화벽 또는 443 포트 문제이고, 인증 오류라면 합법적으로 덤프한 ROM의 NoSSL 패치나 에뮬레이터별 HTTPS 우회가 필요합니다.
- `config.json`의 `upstream_dns`는 인증 등 리디렉션하지 않은 질의를 전달하는 DNS입니다. 기본값은 공개 호환 서버 구현에서 사용된 값이며 언제든 바뀔 수 있습니다.
- DS/DS Lite의 4세대 Wi-Fi는 최신 WPA2/3에 접속하지 못합니다. 격리된 2.4GHz 게스트망, 호환 액세스 포인트 또는 에뮬레이터를 사용하세요. 보안 없는 Wi-Fi를 일반 네트워크와 섞지 마세요.

## 패킷 분석

서버 자체가 보는 애플리케이션 패킷은 `logs/packets.jsonl`에 기록됩니다.

```powershell
# 프로토콜/도메인/경로/DLS 흐름 요약
python analyze_packets.py

# 최근 10개 이벤트
python analyze_packets.py --tail 10

# 이벤트 25의 원문 hex 덤프
python analyze_packets.py --entry 25

# 배포 파일 구조 식별
python analyze_packets.py --file .\my_event.pgf
```

Windows 기본 `pktmon`으로 DNS/HTTP 원시 패킷을 캡처할 수 있습니다. 관리자 PowerShell에서 실행하세요.

```powershell
.\capture_packets.ps1 start
# DS에서 한 번 연결
.\capture_packets.ps1 stop
```

Wireshark/tshark가 설치되어 있으면 생성된 PCAPNG를 CLI에서도 확인할 수 있습니다.

```powershell
python analyze_packets.py --pcap .\logs\ds_capture.pcapng
```

`capture_raw: true`이면 로컬 로그인 토큰을 포함할 수 있는 원문 body가 로그에 Base64로 저장됩니다. 분석 후 `logs` 폴더를 지우거나 `config.json`에서 `capture_raw`를 `false`로 바꾸세요.

## 테스트

```powershell
python -m unittest discover -s tests -v

# 서버를 기본 포트로 실행한 상태에서 DNS/GTS/DLS 실제 소켓 종합 점검
python .\smoke_test.py --server-ip 192.168.137.1
```

## 설정

`config.json` 주요 항목:

| 항목 | 의미 |
|---|---|
| `bind_ip`, `http_port` | HTTP 서버 수신 주소/포트 |
| `dns_bind_ip`, `dns_port` | DNS 서버 수신 주소/포트 |
| `upstream_dns` | 리디렉션하지 않는 DNS 질의의 전달 대상 |
| `public_ip` | DS에 돌려줄 서버 IPv4, `auto`면 자동 감지 |
| `override_domains` | 로컬 서버로 돌릴 도메인 목록 |
| `admin_loopback_only` | 웹 관리 API를 서버 PC로 제한 |
| `local_clients_only` | 모든 DS/GTS/DLS HTTP 요청을 로컬·사설망 주소로 제한 |
| `capture_raw` | 원시 요청 body를 JSONL에 포함할지 여부 |

여러 NIC/VPN 때문에 자동 IP가 틀리면 `public_ip`를 DS와 같은 LAN의 IPv4(예: `192.168.0.25`)로 직접 지정하세요.

## 참고 구현

- [PKHeX](https://github.com/kwsch/PKHeX)
- [MysteryGiftConvert](https://github.com/AdmiralCurtiss/MysteryGiftConvert)
- [IR-GTS](https://github.com/JamieJQuinn/IR-GTS)
- [dwc_network_server_emulator](https://github.com/barronwaffles/dwc_network_server_emulator)

세부 라이선스/참고 범위는 `NOTICE.md`를 확인하세요.

## 현재 폴더 구조와 정리 내역 (2026-09-06)

루트의 모든 폴더가 서버 실행에 필요한 것은 아닙니다.

| 폴더 | 용도 | 실행 시 필요 여부 |
|---|---|---|
| ds_server | 루트 server.py가 불러오는 통합 서버 모듈 | 필요 |
| server | 기존 독립 서버 2개, TLS 인증서 및 과거 DLS 파일 | 현재 server/tls 필요; 나머지는 비교 및 이전 실행용 |
| data | 활성 배포 상태, 업로드한 파일 | 필요 |
| logs | 통신·진단·콘솔 로그 | 실행 중 생성 |
| samples | 변환 예제와 테스트 기준 파일 | 테스트·제작용 |
| tools | 파일 제작기, 뷰어, melonDS 등 | 개발·수동 작업용 |
| reference | 외부 참고 소스 및 보존 자료 | 일반 실행에는 불필요; Gen5GiftMaker 빌드가 upstream/PKHeX-master 참조 |
| tests | 회귀 테스트 | 개발용 |
| 지울것 | 중복 소스·캐시·백업 검토 대기 | 실행에 불필요 |
| .git | 버전 관리 | 서버 실행에는 불필요; 보존 |

- 기존 `DS/` 전체를 `tools/DS/`로 이동했습니다. 뷰어·입력 파일·Obsidian 노트의 내부 구조를 유지했습니다.
- 기존 `기타 파일/` 전체를 `reference/archive_materials/`로 이동했습니다. 고유 자료는 삭제하지 않았습니다.
- 앞서 `지울것/`으로 옮긴 파일의 복원 경로는 당시 경로입니다. 그중 `DS/`는 이제 `tools/DS/`, `기타 파일/`은 이제 `reference/archive_materials/`에 해당합니다.
- ROM 및 SAV는 에뮬레이터에서 참조할 수 있어 현재 위치를 유지했습니다.

## Delta 1.7.3 연결 점검

사용자가 이전에 성공한 구성은 휴대폰 핫스팟 → PC → PC 모바일 핫스팟 → 태블릿 Delta입니다.
태블릿에는 **PC 핫스팟 쪽 IPv4**를 DNS로 입력해야 합니다. PC가 휴대폰에서 받은 상위망 IP와 혼동하지 마세요.

1. PC의 모바일 핫스팟을 먼저 켜고 태블릿을 연결합니다.
2. PC에서 `Get-NetIPAddress -AddressFamily IPv4`로 실제 핫스팟 IPv4를 확인합니다.
3. `start.ps1`로 서버를 시작합니다. `public_ip: auto`는 활성 192.168.137.1이 있으면 우선 사용합니다. 다른 핫스팟 주소라면 config.json의 public_ip를 실제 주소로 지정하세요.
4. Delta 게임의 Wi-Fi 설정에서 기본 DNS를 해당 IP로 지정합니다.
5. PC에서 관리 화면 http://127.0.0.1/ 을 열고 준비된 MYG를 선택합니다.

PC 핫스팟을 켜기 전에 서버를 시작했다면 서버를 재시작해야 합니다. 실행 중 IP를 자동 갱신하지는 않습니다.
2026-09-06 재시작 시점에는 192.168.137.1이 활성화되어 있지 않았고 서버는 172.30.1.100을 표시했습니다.

### 기존 서버와의 호환 작업

- 기존 DNS처럼 nas.nintendowifi.net, conntest.nintendowifi.net에 설정된 WFC 서버 주소를 직접 응답하도록 fixed_dns_records를 추가했습니다. 다른 일반 도메인까지 고정 IP로 응답하지는 않습니다.
- DLS 응답은 기존 서버에 맞춰 HTTP/1.0, 단일 Nintendo Wii Server 헤더, X-DLS-Host를 사용합니다.
- 관리 화면 업로드와 DNS/HTTPS 배포는 루트 server.py 한 프로세스에서 연결됩니다. 기존 server/dns_server.py 및 server/http_server.py를 동시에 실행하면 포트가 충돌합니다.
- HTTPS에 20초 소켓 타임아웃과 단계별 로그를 추가했습니다. ssl3_handshake_complete → ssl3_request_received → ssl3_complete 순서를 확인합니다. 실패 로그의 stage가 멈춘 구간입니다.
- 회귀 테스트 12개 및 실제 로컬 SSLv3 → HTTP → 활성 파일 다운로드가 통과했습니다. Delta/한국어 펄기아 수령 성공을 의미하지는 않습니다.
- 현재 관리 화면에서 사용자가 선택한 Card_0015 파일을 유지했습니다. 공식 배포 여부와 게임 수령 호환성은 확인되지 않았습니다.
