from __future__ import annotations

import ipaddress
import socket
import threading
from pathlib import Path

from .packet_log import PacketLog


class LegacyTlsProxy:
    """Terminate Nintendo DS SSLv3 and forward the decrypted HTTP request locally."""

    def __init__(
        self,
        bind_ip: str,
        port: int,
        backend_port: int,
        cert_file: Path,
        key_file: Path,
        packet_log: PacketLog,
    ) -> None:
        try:
            from tlslite import HandshakeSettings, X509, X509CertChain, parsePEMKey
        except ImportError as exc:
            raise RuntimeError("tlslite-ng가 필요합니다: python -m pip install tlslite-ng") from exc

        certificate = X509()
        certificate.parse(cert_file.read_text(encoding="ascii"))
        private_key = parsePEMKey(key_file.read_text(encoding="ascii"), private=True)

        settings = HandshakeSettings()
        settings.minVersion = (3, 0)
        settings.maxVersion = (3, 0)
        settings.cipherNames = ["rc4"]
        settings.macNames = ["md5", "sha"]

        self.address = (bind_ip, port)
        self.backend_port = backend_port
        self.cert_chain = X509CertChain([certificate])
        self.private_key = private_key
        self.settings = settings
        self.packet_log = packet_log
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(self.address)
        server.listen(16)
        server.settimeout(0.5)
        self._socket = server
        self._thread = threading.Thread(target=self._serve, name="ds-ssl3", daemon=True)
        self._thread.start()

    def close(self) -> None:
        server = self._socket
        self._socket = None
        if server is not None:
            server.close()
        if self._thread is not None:
            self._thread.join(timeout=1)

    def _serve(self) -> None:
        while self._socket is not None:
            try:
                raw_client, address = self._socket.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            threading.Thread(
                target=self._handle,
                args=(raw_client, address),
                name=f"ds-ssl3-{address[0]}",
                daemon=True,
            ).start()

    @staticmethod
    def _read_request(client) -> bytes:
        data = bytearray()
        while b"\r\n\r\n" not in data:
            chunk = client.recv(4096)
            if not chunk:
                raise ConnectionError("HTTP headers truncated")
            data.extend(chunk)
            if len(data) > 64 * 1024:
                raise ValueError("HTTP headers too large")

        header_end = data.index(b"\r\n\r\n") + 4
        headers = data[:header_end].decode("iso-8859-1")
        content_length = 0
        for line in headers.split("\r\n")[1:]:
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":", 1)[1].strip())
                break
        target_length = header_end + content_length
        if target_length > 8 * 1024 * 1024:
            raise ValueError("HTTP request too large")
        while len(data) < target_length:
            chunk = client.recv(min(4096, target_length - len(data)))
            if not chunk:
                raise ConnectionError("HTTP body truncated")
            data.extend(chunk)
        return bytes(data[:target_length])

    @staticmethod
    def _add_client_header(request: bytes, address: str) -> bytes:
        ipaddress.ip_address(address)
        marker = b"\r\n\r\n"
        head, body = request.split(marker, 1)
        return head + f"\r\nX-DS-Client-IP: {address}".encode("ascii") + marker + body

    def _handle(self, raw_client: socket.socket, address: tuple[str, int]) -> None:
        from tlslite import TLSConnection

        peer_ip, peer_port = address
        client = None
        stage = "client_hello"
        try:
            raw_client.settimeout(20)
            first = raw_client.recv(32, socket.MSG_PEEK)
            self.packet_log.write(
                "ssl3_connect", raw=first, client=peer_ip, client_port=peer_port,
            )
            client = TLSConnection(raw_client)
            stage = "handshake"
            client.handshakeServer(
                certChain=self.cert_chain,
                privateKey=self.private_key,
                settings=self.settings,
            )
            self.packet_log.write("ssl3_handshake_complete", client=peer_ip, client_port=peer_port)
            client.ignoreAbruptClose = True
            stage = "http_request"
            request = self._add_client_header(self._read_request(client), peer_ip)
            self.packet_log.write("ssl3_request_received", client=peer_ip, client_port=peer_port)
            stage = "backend_response"
            with socket.create_connection(("127.0.0.1", self.backend_port), timeout=10) as backend:
                backend.sendall(request)
                while True:
                    response = backend.recv(8192)
                    if not response:
                        break
                    client.sendall(response)
            self.packet_log.write("ssl3_complete", client=peer_ip, client_port=peer_port)
        except Exception as exc:
            self.packet_log.write(
                "ssl3_error", client=peer_ip, client_port=peer_port,
                stage=stage, error=f"{type(exc).__name__}: {exc}",
            )
        finally:
            try:
                (client or raw_client).close()
            except Exception:
                pass
