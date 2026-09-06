import socket
from dnslib import DNSRecord, RR, QTYPE, A

# Windows 모바일 핫스팟 인터페이스 IP
HOST_IP = "192.168.0.25"
PUBLIC_WFC_IP = "178.62.43.212"
PORT = 53
# ... (아래 납치 로직은 그대로 유지) ...

def start_dns_server():
    udps = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        udps.bind((HOST_IP, PORT))
        print(f"[*] 스마트 DNS 서버가 {HOST_IP}:{PORT} 에서 대기 중입니다...")
        print(f"[*] 이벤트 서버는 내 컴퓨터로 납치하고, 나머지는 퍼블릭 서버로 패스스루 합니다.\n")
    except Exception as e:
        print(f"[!] 서버 시작 오류: {e}")
        return

    try:
        while True:
            data, addr = udps.recvfrom(1024)
            request = DNSRecord.parse(data)
            qname = str(request.q.qname)
            reply = request.reply()

            # DS 배포 서버 도메인만 내 컴퓨터(HOST_IP)로 납치
            if "gamestats" in qname or "pokemondpds" in qname or "ilostmymind" in qname:
                reply.add_answer(RR(qname, QTYPE.A, rdata=A(HOST_IP), ttl=60))
                print(f"[🎯 타겟 납치] {qname} -> 내 컴퓨터({HOST_IP})로 연결!")

            # 인증(NAS), conntest 등 나머지는 퍼블릭 사설 서버(PUBLIC_WFC_IP)로 토스
            else:
                reply.add_answer(RR(qname, QTYPE.A, rdata=A(PUBLIC_WFC_IP), ttl=60))
                print(f"[➡️ 패스스루] {qname} -> 퍼블릭 서버({PUBLIC_WFC_IP})로 토스!")

            udps.sendto(reply.pack(), addr)

    except KeyboardInterrupt:
        print("\n[*] DNS 서버를 종료합니다.")
    finally:
        udps.close()

if __name__ == '__main__':
    start_dns_server()
