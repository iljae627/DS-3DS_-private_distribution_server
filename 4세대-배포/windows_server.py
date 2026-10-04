#!/usr/bin/env python3
"""Windows-only Generation IV private distribution server."""

from __future__ import annotations

import argparse
import logging
import socketserver
import threading
import time
from pathlib import Path
from urllib.request import urlopen

from pydivert import Direction, WinDivert
from tlslite import HandshakeSettings, SessionCache, TLSConnection, X509, X509CertChain
from tlslite.errors import TLSError
from tlslite.utils.keyfactory import parsePEMKey

import server


LOGGER = logging.getLogger("gen4-windows")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hotspot-ip", default="192.168.137.1", type=server.valid_ipv4)
    parser.add_argument("--gift-dir", default="배포 목록", type=Path)
    parser.add_argument("--upstream-dns", default="167.235.229.36", type=server.valid_ipv4)
    parser.add_argument("--http-port", default=80, type=int)
    parser.add_argument("--https-port", default=443, type=int)
    parser.add_argument("--cert-chain", default="certs/server-chain.crt", type=Path)
    parser.add_argument("--private-key", default="certs/server.key", type=Path)
    parser.add_argument("--log-file", default="diagnostics.log", type=Path)
    return parser.parse_args()


def configure_logging(path: Path) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=(
            logging.StreamHandler(),
            logging.FileHandler(path, mode="w", encoding="utf-8"),
        ),
    )


def prepare_http_server(args: argparse.Namespace) -> server.ThreadingHTTPServer:
    gift_dir = args.gift_dir.resolve()
    gifts = server.load_gift_directory(gift_dir)
    state = server.GiftState(gifts, args.hotspot_ip)
    http_server = server.ThreadingHTTPServer(
        (args.hotspot_ip, args.http_port), server.GiftHandler
    )
    http_server.state = state
    LOGGER.info(
        "[BOOT-HTTP] listening=%s:%d gift_dir=%s gifts=%d myg_bytes=%d",
        args.hotspot_ip,
        args.http_port,
        gift_dir,
        len(gifts),
        server.MYG_SIZE,
    )
    for gift in gifts:
        LOGGER.info("[BOOT-GIFT] wire=%s source=%s", gift.filename, gift.source.name)
    return http_server


class DSHTTPSServer(server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def configure_tls(self, chain_path: Path, key_path: Path) -> None:
        certificates = []
        pem = chain_path.read_text(encoding="ascii")
        marker = "-----END CERTIFICATE-----"
        for part in pem.split(marker):
            if "-----BEGIN CERTIFICATE-----" not in part:
                continue
            cert = X509()
            cert.parse(part + marker + "\n")
            certificates.append(cert)
        if len(certificates) < 2:
            raise RuntimeError("certificate chain must contain server and Wii NWC certificates")
        self.cert_chain = X509CertChain(certificates)
        self.private_key = parsePEMKey(
            key_path.read_text(encoding="ascii"), private=True
        )
        self.session_cache = SessionCache()
        self.tls_settings = HandshakeSettings()
        self.tls_settings.minVersion = (3, 0)
        self.tls_settings.maxVersion = (3, 1)
        self.tls_settings.versions = [(3, 1), (3, 0)]
        self.tls_settings.cipherNames = ["aes128", "3des", "rc4"]
        self.tls_settings.macNames = ["sha", "md5"]
        self.tls_settings.keyExchangeNames = ["rsa"]
        self.tls_settings.useExtendedMasterSecret = False

    def finish_request(self, sock, client_address) -> None:
        tls = TLSConnection(sock)
        try:
            LOGGER.info("[NDS-TLS-01] client-hello client=%s:%d", *client_address)
            tls.handshakeServer(
                certChain=self.cert_chain,
                privateKey=self.private_key,
                sessionCache=self.session_cache,
                settings=self.tls_settings,
            )
            tls.ignoreAbruptClose = True
            LOGGER.info(
                "[NDS-TLS-02] handshake-complete client=%s:%d version=%s cipher=%s",
                client_address[0],
                client_address[1],
                getattr(tls, "versionName", "unknown"),
                getattr(tls, "cipherName", "unknown"),
            )
            self.RequestHandlerClass(tls, client_address, self)
        except TLSError as exc:
            LOGGER.error("[NDS-TLS-ERR] client=%s:%d error=%s", *client_address, exc)
        except Exception:
            LOGGER.exception("[NDS-TLS-ERR] client=%s:%d unexpected failure", *client_address)
        finally:
            try:
                tls.close()
            except Exception:
                pass


def prepare_https_server(args: argparse.Namespace, state: server.GiftState) -> DSHTTPSServer:
    https_server = DSHTTPSServer(
        (args.hotspot_ip, args.https_port), server.GiftHandler
    )
    https_server.state = state
    https_server.configure_tls(args.cert_chain.resolve(), args.private_key.resolve())
    LOGGER.info(
        "[BOOT-HTTPS] listening=%s:%d protocols=SSLv3,TLSv1",
        args.hotspot_ip,
        args.https_port,
    )
    return https_server


def health_check(args: argparse.Namespace) -> None:
    started = time.monotonic()
    with urlopen(f"http://{args.hotspot_ip}:{args.http_port}/health", timeout=5) as response:
        status = response.status
        response.read()
    if status != 200:
        raise RuntimeError(f"HTTP self-test returned {status}")
    LOGGER.info(
        "[SELFTEST-HTTP-PASS] target=%s:%d latency_ms=%.1f",
        args.hotspot_ip,
        args.http_port,
        (time.monotonic() - started) * 1000,
    )


def run_dns_divert(args: argparse.Namespace) -> None:
    packet_filter = (
        f"inbound and ip and ip.DstAddr == {args.hotspot_ip} "
        "and (udp.DstPort == 53 or tcp)"
    )
    LOGGER.info("[BOOT-DNS] opening WinDivert filter=%s", packet_filter)
    nds_clients: set[str] = set()
    with WinDivert(packet_filter, priority=-1000) as divert:
        LOGGER.info("[SELFTEST-DNS-PASS] WinDivert driver opened; waiting for DS queries")
        while True:
            packet = divert.recv()
            original_src = packet.src_addr
            original_dst = packet.dst_addr
            original_src_port = packet.src_port

            if packet.tcp is not None:
                if original_src in nds_clients and (
                    packet.tcp.syn or packet.tcp.rst or packet.tcp.fin
                ):
                    LOGGER.info(
                        "[NDS-TCP-01] client=%s:%d destination=%s:%d syn=%d ack=%d rst=%d fin=%d",
                        original_src,
                        original_src_port,
                        original_dst,
                        packet.dst_port,
                        int(packet.tcp.syn),
                        int(packet.tcp.ack),
                        int(packet.tcp.rst),
                        int(packet.tcp.fin),
                    )
                divert.send(packet)
                continue

            query = bytes(packet.payload or b"")
            try:
                name, qtype, transaction_id = server.dns_query_details(query)
            except (UnicodeDecodeError, ValueError):
                divert.send(packet)
                continue

            if server.is_wfc_name(name):
                nds_clients.add(original_src)

            is_local = server.is_local_distribution_name(name)
            is_nintendo = server.is_wfc_name(name)
            if original_src in nds_clients:
                LOGGER.info(
                    "[NDS-DNS-00] observed client=%s id=%s name=%s qtype=%d classification=%s",
                    original_src,
                    transaction_id,
                    name,
                    qtype,
                    "local-dls" if is_local else ("wfc" if is_nintendo else "pass-through"),
                )

            if not is_nintendo and not is_local:
                divert.send(packet)
                continue

            LOGGER.info(
                "[NDS-DNS-01] captured-direct client=%s:%d id=%s name=%s qtype=%d",
                original_src,
                original_src_port,
                transaction_id,
                name,
                qtype,
            )
            try:
                local_hosts = server.DEFAULT_DLS_HOSTS | ({name} if is_local else set())
                response = server.make_local_dns_response(query, args.hotspot_ip, local_hosts)
                if response is not None:
                    route = "local"
                else:
                    started = time.monotonic()
                    response = server.forward_udp(query, (args.upstream_dns, 53))
                    route = f"WiiLink latency_ms={(time.monotonic() - started) * 1000:.1f}"

                rcode, answers = server.dns_response_details(response)
                packet.src_addr = original_dst
                packet.dst_addr = original_src
                packet.src_port = 53
                packet.dst_port = original_src_port
                packet.payload = response
                packet.direction = Direction.OUTBOUND
                divert.send(packet)
                LOGGER.info(
                    "[NDS-DNS-02] spoofed-direct id=%s route=%s rcode=%d answers=%d bytes=%d",
                    transaction_id,
                    route,
                    rcode,
                    answers,
                    len(response),
                )
            except Exception as exc:
                LOGGER.exception(
                    "[NDS-ERR-DNS] id=%s name=%s error=%s; passing query to ICS",
                    transaction_id,
                    name,
                    exc,
                )
                divert.send(packet)


def main() -> int:
    args = parse_args()
    configure_logging(args.log_file.resolve())
    LOGGER.info("[BOOT-01] Windows-only mode hotspot=%s", args.hotspot_ip)
    http_server = prepare_http_server(args)
    try:
        https_server = prepare_https_server(args, http_server.state)
    except Exception as exc:
        LOGGER.error("[BOOT-HTTPS-FAIL] %s", exc)
        http_server.server_close()
        return 4
    http_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    https_thread = threading.Thread(target=https_server.serve_forever, daemon=True)
    http_thread.start()
    https_thread.start()
    try:
        health_check(args)
    except Exception as exc:
        LOGGER.error("[SELFTEST-HTTP-FAIL] %s", exc)
        http_server.shutdown()
        http_server.server_close()
        https_server.shutdown()
        https_server.server_close()
        return 2

    try:
        run_dns_divert(args)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        LOGGER.error("[SELFTEST-DNS-FAIL] %s", exc)
        return 3
    finally:
        http_server.shutdown()
        http_server.server_close()
        https_server.shutdown()
        https_server.server_close()
        LOGGER.info("[STOP-01] Windows DNS interception and HTTP/HTTPS servers stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
