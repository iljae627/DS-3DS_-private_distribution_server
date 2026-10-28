# 포켓몬 6세대 한국판 사설 배포 서버

포켓몬 X, Y, 오메가루비, 알파사파이어의 `이상한 소포 → 인터넷으로 받기` 요청을 로컬 PC로 연결한다. `배포파일`의 264바이트 WC6를 784바이트 WC6Full로 포장하고, 본인 3DS에서 덤프한 BOSS AES 키로 컨테이너를 생성한다.

## 지원 게임

| 게임 | BOSS App ID | Title ID |
|---|---|---|
| X | `h0VRqB2YEgq39zvO` | `0004000000055D00` |
| Y | `Slv7vHlUOfqrKMpz` | `0004000000055E00` |
| 오메가루비 | `cRFY0WFHNjPh44If` | `000400000011C400` |
| 알파사파이어 | `guBwm9TlQvYvncKn` | `000400000011C500` |

언어와 NPFL 속성은 한국(`KR`, `ko`, `MYS_KR_K`)으로 고정된다.

## 3DS 준비

1. Luma3DS의 `Enable game patching`을 켠다.
2. SSL 검증 해제 패치를 SD 카드의 `luma/sysmodules/0004013000002F02.ips`에 넣는다.
3. BOSS RSA 서명 검사를 허용하는 Luma/Pretendo 계열 패치를 적용한다. 자체 생성 BOSS에는 Nintendo RSA 서명이 없으므로 이 패치가 없으면 거부된다.
4. GodMode9 DumpKeys로 생성한 `SD:/gm9/aes_keys.txt`를 PC로 가져온 뒤 `./install-key.ps1`을 실행하여 파일을 선택한다. 스크립트가 `keys/aes_keys.txt`에 안전하게 복사하고 `slot0x38KeyN` 형식을 검사한다.

키 파일과 생성된 서버 개인키는 `.gitignore` 처리된다. 키 내용을 채팅이나 저장소에 올리지 않는다.

## 실행

관리자 PowerShell에서 실행한다. DNS 53번, 접속 테스트용 HTTP 80번 및 HTTPS 443번 포트를 열기 위해 관리자 권한이 필요하다.

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\start-server.ps1
```

처음 실행할 때 npm 의존성 설치와 자체 HTTPS 인증서 생성이 자동으로 수행된다. 화면에 표시된 IPv4 주소를 3DS 인터넷 설정의 기본 DNS와 보조 DNS에 모두 입력한다. Windows 방화벽에서 Python의 개인 네트워크 통신을 허용한다.

주소를 직접 지정하려면 `./start-server.ps1 -ServerIp 192.168.0.10`처럼 실행한다. 파일 선택 화면에서 `0`은 매 요청 무작위다. `-Select random`으로 바로 무작위 실행할 수도 있다.

## 배포 파일

`배포파일` 바로 아래에 `.wc6` 파일을 추가한 뒤 서버를 다시 시작한다. 모든 파일은 정확히 264바이트여야 한다. 서버는 게임별 WC6Full 수신 플래그, 한국어 제한, CRC16을 생성한다.

## 확인 순서

1. PC에서 서버를 관리자 권한으로 시작한다.
2. 3DS DNS를 화면의 PC 주소로 설정한다.
3. 3DS를 완전히 재부팅해 Luma 패치를 적용한다.
4. X/Y/OR/AS 실행 후 `이상한 소포 → 소포를 받는다 → 인터넷으로 받는다`를 선택한다.
5. 서버 로그에서 `filelist` 다음 `nsa` 요청이 이어지는지 확인한다.

연결에 실패하면 53/443 포트 충돌, Windows 방화벽, SSL IPS 경로를 확인한다. 목록은 오지만 카드 저장에 실패하면 BOSS RSA 서명 패치 또는 게임별 WC6 호환성을 확인한다.

## 테스트

```powershell
npm install
python -m unittest -v test_server.py
```

Nintendo의 인증서, 개인키 또는 서비스 자격증명은 포함하지 않는다. BOSS 대칭키는 사용자가 소유한 기기에서 직접 덤프한 값을 로컬에서만 사용한다.
