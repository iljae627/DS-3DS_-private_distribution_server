import base64
import json
import socket
import struct
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

from ds_server.dns_server import DnsProxy
from ds_server.http_server import DsHttpServer
from ds_server.packet_log import PacketLog


class LegacyCompatibilityTests(unittest.TestCase):
    def test_dns_local_distribution_and_fixed_auth_records(self):
        with tempfile.TemporaryDirectory() as directory:
            log = PacketLog(Path(directory) / "packets.jsonl", False)
            dns = DnsProxy("127.0.0.1", 0, "192.168.137.1",
                           ["dls1.ilostmymind.xyz"], "127.0.0.1", 9, log,
                           fixed_records={"nas.nintendowifi.net": "192.0.2.10"})
            dns.start()
            forwarding = threading.Event()
            release = threading.Event()
            def stalled_upstream(packet):
                forwarding.set()
                release.wait(5)
                return None
            dns._forward = stalled_upstream
            try:
                # An unrelated stalled lookup must not hold up WFC responses.
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                    sender.sendto(b"\x12\x35\x01\x00\x00\x01" + b"\0" * 6
                                  + b"\x07example\x03com\0" + struct.pack("!HH", 1, 1),
                                  dns.socket.getsockname())
                self.assertTrue(forwarding.wait(1))
                for name, expected in [("dls1.ilostmymind.xyz", "192.168.137.1"),
                                       ("nas.nintendowifi.net", "192.0.2.10")]:
                    labels = b"".join(bytes([len(s)]) + s.encode() for s in name.split(".")) + b"\0"
                    query = b"\x12\x34\x01\x00\x00\x01" + b"\0" * 6 + labels + struct.pack("!HH", 1, 1)
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                        client.settimeout(2)
                        client.sendto(query, dns.socket.getsockname())
                        result = client.recv(4096)
                    self.assertEqual(result[:2], query[:2])
                    self.assertEqual(socket.inet_ntoa(result[-4:]), expected)
            finally:
                release.set()
                dns.close()
                dns.thread.join(timeout=2)

    def test_gen4_uploaded_wire_file_reaches_dls_with_legacy_headers(self):
        fixture = Path(__file__).resolve().parents[1] / "samples/reference/mew_reference.myg"
        if not fixture.is_file():
            self.skipTest("Local distribution fixture is not included in the repository")
        wire = fixture.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            server = DsHttpServer(("127.0.0.1", 0), root, "127.0.0.1",
                                  PacketLog(root / "packets.jsonl", False), True)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                payload = json.dumps({"kind": "gen4", "file_name": "reference.myg",
                                      "data_base64": base64.b64encode(wire).decode()}).encode()
                request = urllib.request.Request(base + "/admin/upload", data=payload,
                                                 headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=3) as response:
                    self.assertTrue(json.load(response)["ok"])
                for action in ("count", "list", "contents"):
                    body = urllib.parse.urlencode({"action": action, "gamecd": "APAK"}).encode()
                    with urllib.request.urlopen(base + "/download", data=body, timeout=3) as response:
                        self.assertEqual(response.version, 10)
                        self.assertEqual(response.headers.get_all("Server"), ["Nintendo Wii (http)"])
                        self.assertEqual(response.headers["X-DLS-Host"], "http://127.0.0.1/")
                        content = response.read()
                    if action == "count":
                        self.assertEqual(content, b"1")
                    elif action == "list":
                        self.assertTrue(content.endswith(b"\t936\r\n"))
                    else:
                        self.assertEqual(content, wire)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=2)
