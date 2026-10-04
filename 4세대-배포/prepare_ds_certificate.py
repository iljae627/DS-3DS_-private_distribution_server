#!/usr/bin/env python3
"""Create a DS-trusted local server certificate from the Wii NWC bundle."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p12", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    ca_key, ca_cert, _ = pkcs12.load_key_and_certificates(
        args.p12.read_bytes(), b"alpine"
    )
    if ca_key is None or ca_cert is None:
        raise RuntimeError("Wii NWC bundle does not contain a key and certificate")

    server_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    now = datetime.now(timezone.utc)
    subject = x509.Name(
        [
            x509.NameAttribute(x509.NameOID.ORGANIZATION_NAME, "Private Gen4 DLS"),
            x509.NameAttribute(x509.NameOID.COMMON_NAME, "*.*.*"),
        ]
    )
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("dls1.ilostmymind.xyz"),
                    x509.DNSName("dls1.nintendowifi.net"),
                    x509.DNSName("*.nintendowifi.net"),
                ]
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA1())
    )

    key_path = args.output / "server.key"
    chain_path = args.output / "server-chain.crt"
    key_path.write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    chain_path.write_bytes(
        certificate.public_bytes(serialization.Encoding.PEM)
        + ca_cert.public_bytes(serialization.Encoding.PEM)
    )
    print(f"Created {chain_path} and {key_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
