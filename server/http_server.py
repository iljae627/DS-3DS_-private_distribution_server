import base64
import os
import socket
import threading
from email.utils import formatdate
from pathlib import Path
from urllib.parse import parse_qs, unquote_plus

from tlslite import (
    HandshakeSettings,
    TLSConnection,
    TLSError,
    X509,
    X509CertChain,
    parsePEMKey,
)

BASE_DIR = Path(__file__).resolve().parent
CERT_FILE = BASE_DIR / "tls" / "dls1-cert.pem"
KEY_FILE = BASE_DIR / "tls" / "dls1-key.pem"
DLC_DIR = BASE_DIR / "dlc" / "CPUK"

# Keep a single deterministic offer during protocol validation.
OFFER_FILE = os.environ.get("DLS_OFFER_FILE", "arceus_custom.myg")


def read_http_request(client):
    """Read one complete HTTP request, including a fragmented POST body."""
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = client.recv(4096)
        if not chunk:
            raise ConnectionError("HTTP headers truncated")
        data += chunk
        if len(data) > 16384:
            raise ValueError("HTTP headers too large")

    header_end = data.index(b"\r\n\r\n") + 4
    header_text = data[:header_end].decode("iso-8859-1")
    body = data[header_end:]
    lines = header_text.split("\r\n")
    method, path, _version = lines[0].split(" ", 2)

    content_length = 0
    for line in lines[1:]:
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":", 1)[1].strip())
            break

    while len(body) < content_length:
        chunk = client.recv(content_length - len(body))
        if not chunk:
            raise ConnectionError("HTTP body truncated")
        body += chunk

    return method, path, bytes(body)


def decode_dls_value(value):
    """Accept raw fields and Nintendo's base64 URL substitutions."""
    value = unquote_plus(value)
    try:
        encoded = value.replace("*", "=").replace("?", "/").replace(">", "+")
        decoded = base64.b64decode(encoded, validate=True).decode("ascii")
        if decoded.isprintable():
            return decoded
    except Exception:
        pass
    return value


def parse_dls_form(body):
    raw = parse_qs(body.decode("ascii", "replace"), keep_blank_values=True)
    return {key: decode_dls_value(values[0]) for key, values in raw.items()}


def send_http(client, body, content_type="text/plain", filename=None):
    """Match the headers emitted by the reference dls1_server.py."""
    headers = [
        "HTTP/1.0 200 OK",
        "Server: Nintendo Wii (http)",
        f"Date: {formatdate(usegmt=True)}",
        f"Content-type: {content_type}",
    ]
    if filename:
        headers.append(f'Content-Disposition: attachment; filename="{filename}"')
    headers.extend((
        "X-DLS-Host: http://127.0.0.1/",
        f"Content-Length: {len(body)}",
    ))
    client.sendall(("\r\n".join(headers) + "\r\n\r\n").encode("ascii") + body)


def handle_dls_request(client, addr, protocol):
    try:
        method, path, body = read_http_request(client)
        if method != "POST" or path.split("?", 1)[0] != "/download":
            raise ValueError(f"unexpected request: {method} {path}")

        post = parse_dls_form(body)
        action = post.get("action", "")
        gamecd = post.get("gamecd", "")
        print(f"[DLS1] {addr[0]} action={action} gamecd={gamecd}")

        if gamecd not in {"CPUK", "APAK"}:
            raise ValueError(f"unsupported game code: {gamecd}")

        offer = DLC_DIR / OFFER_FILE
        if not offer.is_file():
            raise FileNotFoundError(f"missing offer file: {offer}")

        if action == "count":
            send_http(client, b"1")
        elif action == "list":
            # dls1_server.py sends one selected Gen 4 record, terminated by CRLF.
            listing = f"{OFFER_FILE}\t\t\t\t\t{offer.stat().st_size}\r\n"
            send_http(client, listing.encode("ascii"))
        elif action == "contents":
            requested = Path(post.get("contents", "")).name
            if requested != OFFER_FILE:
                raise ValueError(f"unexpected contents request: {requested}")
            send_http(
                client,
                offer.read_bytes(),
                content_type="application/x-dsdl",
                filename=OFFER_FILE,
            )
            print(f"[*] DLS1 contents sent: {OFFER_FILE}")
        else:
            raise ValueError(f"unsupported DLS1 action: {action}")
    except Exception as e:
        print(f"[!] DLS1 request failed: {e}")
    finally:
        client.close()


def handle_ssl3_client(raw_client, addr, cert_chain, private_key, settings):
    try:
        first_bytes = raw_client.recv(32, socket.MSG_PEEK)
        print(f"[*] HTTPS TCP from {addr[0]}:{addr[1]} first-bytes={first_bytes.hex(' ')}")
        client = TLSConnection(raw_client)
        client.handshakeServer(certChain=cert_chain, privateKey=private_key, settings=settings)
        client.ignoreAbruptClose = True
        handle_dls_request(client, addr, "SSLv3/HTTPS")
    except TLSError as e:
        print(f"[!] SSLv3 handshake failed from {addr[0]}:{addr[1]}: {e}")
        raw_client.close()
    except Exception as e:
        print(f"[!] SSLv3 server error from {addr[0]}:{addr[1]}: {e}")
        raw_client.close()


def serve(port, ssl3_parameters=None):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", port))
    server.listen(16)
    print(f"[*] {'HTTPS' if ssl3_parameters else 'HTTP'} listening on 0.0.0.0:{port}")

    while True:
        client, addr = server.accept()
        if ssl3_parameters:
            target = handle_ssl3_client
            args = (client, addr, *ssl3_parameters)
        else:
            target = handle_dls_request
            args = (client, addr, "HTTP")
        threading.Thread(target=target, args=args, daemon=True).start()


def main():
    offer = DLC_DIR / OFFER_FILE
    if not offer.is_file():
        raise FileNotFoundError(f"DLS offer is missing: {offer}")
    if not CERT_FILE.is_file() or not KEY_FILE.is_file():
        raise FileNotFoundError("dls1-cert.pem / dls1-key.pem is missing")
    print(f"[*] DLS offer: {offer.name} ({offer.stat().st_size} bytes)")

    certificate = X509()
    certificate.parse(CERT_FILE.read_text(encoding="ascii"))
    private_key = parsePEMKey(KEY_FILE.read_text(encoding="ascii"), private=True)
    cert_chain = X509CertChain([certificate])

    settings = HandshakeSettings()
    settings.minVersion = (3, 0)
    settings.maxVersion = (3, 0)
    settings.cipherNames = ["rc4"]
    settings.macNames = ["md5", "sha"]

    threading.Thread(target=serve, args=(80,), daemon=True).start()
    serve(443, (cert_chain, private_key, settings))


if __name__ == "__main__":
    main()
