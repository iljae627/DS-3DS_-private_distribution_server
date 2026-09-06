from __future__ import annotations

import base64
import os
import struct
import tempfile
import threading
import unittest
import json
import urllib.parse
import urllib.request
from pathlib import Path

from ds_server.dns_server import build_a_response, parse_question
from ds_server.gift_converter import crc16_ccitt, gen4_pcd_to_dls, gen5_pgf_to_dls, gift_metadata
from ds_server.pokemon import decrypt_pk4, encrypt_pk4
from ds_server.protocol import decode_dls_form
from ds_server.http_server import DsHttpServer
from ds_server.packet_log import PacketLog


def dns_query(name: str) -> bytes:
    labels = b"".join(bytes((len(part),)) + part.encode() for part in name.split(".")) + b"\0"
    return b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + labels + struct.pack("!HH", 1, 1)


def dls_b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode().replace("=", "*")


class CoreTests(unittest.TestCase):
    def test_pk4_encryption_roundtrip_party(self) -> None:
        clear = os.urandom(236)
        encrypted = encrypt_pk4(clear)
        self.assertNotEqual(clear[8:], encrypted[8:])
        self.assertEqual(clear, decrypt_pk4(encrypted))

    def test_gen4_conversion(self) -> None:
        pcd = bytearray(856)
        pcd[0x10:0x12] = (25).to_bytes(2, "little")
        pcd[0x150:0x152] = (123).to_bytes(2, "little")
        result = gen4_pcd_to_dls(bytes(pcd))
        self.assertEqual(936, len(result))
        self.assertEqual(pcd[0x104:0x154], result[:0x50])
        self.assertEqual(123, gift_metadata(result)["card_id"])

    def test_gen5_conversion_and_crc(self) -> None:
        pgf = bytearray(204)
        pgf[0xB0:0xB2] = (456).to_bytes(2, "little")
        pgf[0x1A:0x1C] = (494).to_bytes(2, "little")
        result = gen5_pgf_to_dls(bytes(pgf), "테스트\nGift", "k", "bw2")
        self.assertEqual(720, len(result))
        self.assertEqual(crc16_ccitt(result[:-2]), int.from_bytes(result[-2:], "little"))
        self.assertEqual(8, result[0x2CB])
        self.assertEqual(456, gift_metadata(result)["card_id"])

    def test_dls_form_decoding(self) -> None:
        body = f"action={dls_b64('count')}&gamecd={dls_b64('IRAO')}&attr1={dls_b64('MYSTERY_K')}".encode()
        fields = decode_dls_form(body)
        self.assertEqual("count", fields["action"])
        self.assertEqual("IRAO", fields["gamecd"])
        self.assertEqual("MYSTERY_K", fields["attr1"])

    def test_dns_override_response(self) -> None:
        query = dns_query("gamestats2.gs.nintendowifi.net")
        domain, qtype, end = parse_question(query)
        response = build_a_response(query, end, "192.168.10.5")
        self.assertEqual("gamestats2.gs.nintendowifi.net", domain)
        self.assertEqual(1, qtype)
        self.assertEqual(b"\x12\x34", response[:2])
        self.assertEqual(b"\xC0\xA8\x0A\x05", response[-4:])

    def test_http_upload_and_gen5_dls_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = PacketLog(root / "logs" / "packets.jsonl", capture_raw=False)
            server = DsHttpServer(("127.0.0.1", 0), root, "127.0.0.1", log, True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                pgf = bytearray(204)
                pgf[0xB0:0xB2] = (77).to_bytes(2, "little")
                payload = json.dumps({
                    "kind": "gen5", "file_name": "test.pgf",
                    "data_base64": base64.b64encode(pgf).decode(),
                    "language": "k", "versions": "wbw2b2", "description": "test",
                }).encode()
                request = urllib.request.Request(
                    base + "/admin/upload", data=payload,
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                with urllib.request.urlopen(request) as response:
                    uploaded = json.load(response)
                self.assertTrue(uploaded["ok"])

                def dls(action: str, contents: str = "") -> bytes:
                    values = {"action": dls_b64(action), "gamecd": dls_b64("IRAO")}
                    if contents:
                        values["contents"] = dls_b64(contents)
                    body = urllib.parse.urlencode(values).encode()
                    req = urllib.request.Request(base + "/download", data=body, method="POST")
                    with urllib.request.urlopen(req) as response:
                        return response.read()

                self.assertEqual(b"1", dls("count"))
                listing = dls("list")
                self.assertIn(b"G0077.bin", listing)
                self.assertEqual(720, len(dls("contents", "G0077.bin")))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
