from datetime import datetime, timedelta, timezone
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
root=Path(__file__).resolve().parent; out=root/"certs"/"server.pem"; out.parent.mkdir(exist_ok=True)
key=rsa.generate_private_key(public_exponent=65537,key_size=2048); name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,"Gen6 Private Distribution")]); now=datetime.now(timezone.utc)
cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=3650)).add_extension(x509.SubjectAlternativeName([x509.DNSName(x) for x in ("nppl.c.app.nintendowifi.net","npfl.c.app.nintendowifi.net","npdl.cdn.nintendowifi.net","3ds-fushigi.pokemon-gl.com")]),critical=False).sign(key,hashes.SHA256()))
out.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.TraditionalOpenSSL,serialization.NoEncryption())+cert.public_bytes(serialization.Encoding.PEM)); print(out)
