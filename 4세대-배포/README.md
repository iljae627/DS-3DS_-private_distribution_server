# 4세대 사설 배포 서버

첨부받은 일본어 4세대 Wonder Card 한 장을 정품 게임의 `이상한 소포 -> Nintendo WFC로 받기`에서 내려주는 전용 서버다.

## 구성

- Windows 핫스팟/ICS: DS용 DHCP와 인터넷 NAT 제공
- Windows Python: 핫스팟 주소 `192.168.137.1:80`에서 연결 테스트와 DLS를 직접 제공
- TLSLite: DS용 SSLv3/TLSv1 HTTPS `192.168.137.1:443`에서 같은 DLS를 제공
- WinDivert: DS에서 핫스팟 DNS로 들어오는 패킷 중 Nintendo/Wiimmfi 질의만 직접 응답
- WiiLink DNS `167.235.229.36`: 정품 카트리지의 Nintendo WFC NAS/구형 SSL 인증 처리
- 로컬 연결 테스트: `conntest.nintendowifi.net`의 HTTP 200 응답을 PC에서 직접 제공
- 로컬 DNS: WFC 인증 호스트는 WiiLink로 전달하고 모든 알려진 DLS 호스트만 로컬 서버로 매핑
- 카드: `배포 목록`의 모든 `.pcd`; DS의 `list` 요청마다 하나를 무작위 선택

`\배포 목록`에 856바이트 PCD 파일을 자유롭게 넣고 서버를 시작한다. 서버는 시작할 때 모든 PCD를 검증하며, 하나라도 크기가 틀리면 문제 파일명을 로그에 남기고 시작을 중단한다. 파일을 추가·삭제한 뒤에는 서버를 다시 시작한다.

서버는 인터넷 연결이 필요하다. 인증은 외부 WFC 대체 서버를 사용하지만 Wonder Card 파일은 외부에 업로드하지 않으며 이 PC에서만 제공한다.

## 최초 1회 준비

WSL은 필요하지 않다. 프로젝트의 `.venv`에 Windows Python, PyDivert, TLSLite가 준비되어 있다. WinDivert 드라이버와 80/443번 포트를 사용하므로 관리자 PowerShell에서 실행한다.

`start-server.ps1`은 첫 실행 때 Wii NWC PKCS#12 묶음을 다운로드하고 SHA-256을 검증한 뒤, DS가 신뢰할 로컬 서버 인증서를 `certs`에 생성한다. 이후에는 인터넷 다운로드 없이 실행된다. `WII_NWC_1_CERT.p12`와 `certs/server.key`는 외부에 공유하지 않는다.

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

## 실행

1. PC를 집 공유기나 휴대폰 핫스팟에 연결한다.
2. PC에서 DS가 접속할 수 있는 **2.4GHz 무암호 핫스팟**을 켠다. `제어판 -> 네트워크 및 인터넷 -> 네트워크 및 공유 센터 -> 어댑터 설정 변경 -> 핫스팟 무선 속성 -> 보안`에서 보안 종류를 `없음/Open`으로 둔다. 이것은 Wi-Fi 암호화를 끄는 설정이며 Windows Defender 방화벽 전체를 끄는 것이 아니다.
3. 이 폴더에서 **관리자 PowerShell**을 열고 실행한다.

   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   .\start-server.ps1
   ```

4. 화면에 표시된 핫스팟 주소 `192.168.137.1`을 DS 연결 설정의 기본 DNS와 보조 DNS에 똑같이 입력한다.
5. 자동 IP 받기는 켜 둔다.
6. 게임에서 `이상한 소포 -> 소포를 받는다 -> Nintendo WFC로 받는다`를 선택한다.

핫스팟 주소가 다른 환경에서는 직접 지정한다.

```powershell
.\start-server.ps1 -HotspotIp 192.168.137.1
```

서버 로그에 다음 흐름이 보여야 한다.

```text
[SELFTEST-HTTP-PASS]
[SELFTEST-DNS-PASS] WinDivert driver opened
[BOOT-HTTPS] listening=192.168.137.1:443 protocols=SSLv3,TLSv1
[NDS-DNS-01] captured-direct
[NDS-DNS-02] spoofed-direct
[NDS-HTTP-01] connection-test-request
[NDS-TLS-02] handshake-complete
[NDS-GIFT-SELECT] selected=private-gift-001.myg source=gift.pcd pool=1
[NDS-DLS-01] request action=contents
```

서버는 핫스팟으로 들어오는 DNS만 검사하며 Nintendo/Wiimmfi가 아닌 질의는 변경 없이 ICS에 돌려준다. PC 자체의 DNS는 캡처하지 않는다. `[NDS-DNS-01/02]`는 DS 질의 캡처와 직접 응답, `[NDS-HTTP-01/02]`는 연결 테스트, `[NDS-DLS-01/02]`는 선물 전송 단계다.

DS로 식별된 IP의 모든 DNS 이름은 `[NDS-DNS-00]`으로 기록한다. 이름에 `dls` 또는 `dsdl` 레이블이 있으면 알려지지 않은 도메인이어도 공개 배포 서버로 보내지 않고 무조건 로컬 주소로 응답한다. `[NDS-DLS-01] request action=contents`와 `[NDS-DLS-02]`가 모두 없으면 이 서버는 어떤 선물도 전송하지 않은 것이다.

`[NDS-TCP-01]`은 DS가 로컬 서버로 보내는 TCP 연결 시작/종료를 기록한다. `destination=192.168.137.1:80 syn=1` 다음에 `[NDS-HTTP-01]`이 없다면 Windows TCP/방화벽 구간 문제이며, 목적지 포트가 80이 아니면 해당 DLS 포트를 서버에 추가해야 한다.

전체 진단은 `diagnostics.log`에 저장된다.

`DLS request action=contents`가 찍히지 않았다면 로컬 선물이 전송된 것이 아니다. 공개 서버의 다른 선물을 받은 적이 있다면 받은 카드와 수령 기록을 지운 뒤 다시 시도한다.

## 카드 및 게임 주의사항

- 원본 파일은 일본어 카드이므로 일본판 게임을 대상으로 한다.
- 게임 버전 호환 여부는 카드 내부 플래그를 따른다.
- 4세대는 Wonder Card를 최대 3장 보관한다. 공간이 없으면 기존 카드를 삭제해야 한다.
- 같은 Card ID의 수령 기록이 있으면 다시 받지 못할 수 있다.
- 배달원에게 선물을 받은 뒤 저장해야 한다.

`..\배포파일 변환기`는 현재 **제작 중**이며, 아직 실제 배포용 PCD 생성에 사용하지 않는다.

## 진단

자동 테스트:

```bash
.\.venv\Scripts\python.exe -m unittest -v test_server.py
```

포트 점유 확인:

```powershell
Get-NetTCPConnection -LocalPort 80 -ErrorAction SilentlyContinue
```

- DS 연결 테스트부터 실패: 핫스팟이 무암호·2.4GHz·802.11b/g 호환인지 확인한다.
- `192.168.137.1:53`을 `svchost`가 쓰는 것은 정상이다. WinDivert가 Nintendo DNS 패킷을 그 앞에서 가로챈다.
- `[SELFTEST-DNS-FAIL]`: 관리자 권한, 보안 프로그램의 드라이버 차단, 또는 WinDivert 로딩 문제다.
- `count/list/contents`가 없음: DS의 DNS가 핫스팟 IP인지 확인하고 앞선 단계 ID를 확인한다.
- NAS 단계 오류: 인터넷 연결 또는 WiiLink 인증 서버 문제일 수 있다.
- 일반 PC 도메인은 캡처 대상이 아니므로 로그에 나타나지 않는다.
- 오류 `60000`: 다른 사설 WFC에서 만든 프로필 충돌일 수 있다. 세이브 백업 후 Nintendo WFC 설정 초기화를 검토한다.

## 구현 근거

- `MYG = PCD[0x104:0x154] + PCD` 형식
- Nintendo DLS `/download`의 `count`, `list`, `contents` 작업
- 정품 게임 SSL 인증은 `nds-constraint` 호환 공개 NAS에 위임
- WSL NAT 네트워크를 사용하여 Windows 모바일 핫스팟의 ICS DNS와 로컬 서버의 53번 포트를 분리

## 설정 복원

관리자 PowerShell에서 아래를 실행한 뒤 모바일 핫스팟을 껐다가 다시 켠다.

```powershell
.\restore-wsl-network.ps1
```

참고 구현:

- https://github.com/barronwaffles/dwc_network_server_emulator
- https://github.com/KaeruTeam/nds-constraint
- https://github.com/vixthevix/IVgift

