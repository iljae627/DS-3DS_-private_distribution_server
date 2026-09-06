from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ds_server.dns_server import DnsProxy
from ds_server.http_server import DsHttpServer
from ds_server.legacy_tls import LegacyTlsProxy
from ds_server.network import detect_server_ip
from ds_server.packet_log import PacketLog


ROOT = Path(__file__).resolve().parent


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def main() -> int:
    parser = argparse.ArgumentParser(description="Nintendo DS Pokémon private distribution server")
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--http-port", type=int)
    parser.add_argument("--dns-port", type=int)
    parser.add_argument("--no-dns", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.http_port is not None:
        config["http_port"] = args.http_port
    if args.dns_port is not None:
        config["dns_port"] = args.dns_port

    public_ip = config.get("public_ip", "auto")
    if public_ip == "auto":
        public_ip = detect_server_ip(config["upstream_dns"])
    dns_bind_ip = config.get("dns_bind_ip", "0.0.0.0")
    if dns_bind_ip == "auto":
        dns_bind_ip = public_ip
    packet_log = PacketLog(ROOT / "logs" / "packets.jsonl", bool(config.get("capture_raw", True)))

    dns: DnsProxy | None = None
    if not args.no_dns:
        dns = DnsProxy(
            dns_bind_ip, int(config.get("dns_port", 53)),
            public_ip, config["override_domains"], config["upstream_dns"],
            int(config.get("upstream_dns_port", 53)), packet_log,
            fixed_records=config.get("fixed_dns_records", {}),
        )
        try:
            dns.start()
        except OSError as exc:
            print(f"[경고] DNS 서버를 열지 못했습니다: {exc}", file=sys.stderr)
            print("       관리자 권한/포트 53 사용 여부를 확인하세요.", file=sys.stderr)
            dns = None

    try:
        httpd = DsHttpServer(
            (config.get("bind_ip", "0.0.0.0"), int(config.get("http_port", 80))),
            ROOT, public_ip, packet_log, bool(config.get("admin_loopback_only", True)),
            bool(config.get("local_clients_only", True)),
        )
    except OSError as exc:
        if dns:
            dns.close()
        print(f"[오류] HTTP 서버를 열지 못했습니다: {exc}", file=sys.stderr)
        return 2

    legacy_tls: LegacyTlsProxy | None = None
    if bool(config.get("enable_legacy_https", True)):
        cert_file = ROOT / str(config.get("tls_cert", "server/tls/dls1-cert.pem"))
        key_file = ROOT / str(config.get("tls_key", "server/tls/dls1-key.pem"))
        try:
            legacy_tls = LegacyTlsProxy(
                config.get("bind_ip", "0.0.0.0"), int(config.get("https_port", 443)),
                int(config.get("http_port", 80)), cert_file, key_file, packet_log,
            )
            legacy_tls.start()
        except Exception as exc:
            print(f"[경고] DS 레거시 HTTPS 서버를 열지 못했습니다: {exc}", file=sys.stderr)
            legacy_tls = None

    port = httpd.server_address[1]
    suffix = "" if port == 80 else f":{port}"
    print("=" * 64)
    print(" Nintendo DS Pokémon Private Distribution Server")
    print("=" * 64)
    print(f"관리 화면 : http://127.0.0.1{suffix}/")
    print(f"DS 기본 DNS: {public_ip}" + ("" if dns else " (DNS 서버 시작 실패)"))
    https_status = "" if legacy_tls else " (시작 실패)" if config.get("enable_legacy_https", True) else " (이 프로세스에서 비활성)"
    print("DS 배포 HTTPS: SSLv3/443" + https_status)
    print(f"패킷 로그 : {ROOT / 'logs' / 'packets.jsonl'}")
    print("종료: Ctrl+C")
    try:
        httpd.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\n서버를 종료합니다.")
    finally:
        httpd.server_close()
        if legacy_tls:
            legacy_tls.close()
        if dns:
            dns.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
