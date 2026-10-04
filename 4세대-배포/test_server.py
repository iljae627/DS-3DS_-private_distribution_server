import struct
import socket
import tempfile
import threading
import unittest

import server
import windows_server
from tlslite import HandshakeSettings, TLSConnection


def dns_query(name: str, qtype: int = 1) -> bytes:
    labels = b"".join(bytes([len(part)]) + part.encode("ascii") for part in name.split("."))
    return b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + labels + b"\x00" + struct.pack("!HH", qtype, 1)


class ServerTests(unittest.TestCase):
    def test_pcd_to_myg(self):
        pcd = bytes((index % 251 for index in range(server.PCD_SIZE)))
        myg = server.pcd_to_myg(pcd)
        self.assertEqual(len(myg), server.MYG_SIZE)
        self.assertEqual(myg[:0x50], pcd[0x104:0x154])
        self.assertEqual(myg[0x50:], pcd)

    def test_rejects_wrong_pcd_size(self):
        with self.assertRaises(ValueError):
            server.pcd_to_myg(b"short")

    def test_decodes_nintendo_dls_values(self):
        self.assertEqual(server.decode_dls_value("Y291bnQ*"), "count")
        self.assertEqual(server.decode_dls_value("bGlzdA**"), "list")
        self.assertEqual(server.decode_dls_value("QURBSw**"), "ADAK")
        self.assertEqual(server.decode_dls_value("contents"), "contents")

    def test_loads_all_pcd_files_and_selects_one_per_client(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = server.Path(temporary)
            (directory / "a.pcd").write_bytes(bytes(server.PCD_SIZE))
            (directory / "B.PCD").write_bytes(bytes([1]) * server.PCD_SIZE)
            (directory / "ignore.txt").write_text("ignored")
            gifts = server.load_gift_directory(directory)
            self.assertEqual([gift.filename for gift in gifts], ["private-gift-001.myg", "private-gift-002.myg"])
            state = server.GiftState(gifts, "127.0.0.1")
            chosen = state.choose("192.168.137.253")
            self.assertIs(state.selected("192.168.137.253", chosen.filename), chosen)
            self.assertIsNone(state.selected("192.168.137.253", "other.myg"))

    def test_local_dns_a_response(self):
        response = server.make_local_dns_response(
            dns_query("dls1.nintendowifi.net"),
            "192.168.137.1",
            server.DEFAULT_DLS_HOSTS,
        )
        self.assertIsNotNone(response)
        self.assertEqual(response[:2], b"\x12\x34")
        self.assertEqual(response[-4:], bytes([192, 168, 137, 1]))

    def test_connection_test_is_local(self):
        response = server.make_local_dns_response(
            dns_query("conntest.nintendowifi.net"),
            "192.168.137.1",
            server.DEFAULT_DLS_HOSTS,
        )
        self.assertIsNotNone(response)
        self.assertEqual(response[-4:], bytes([192, 168, 137, 1]))

    def test_unrelated_dns_is_not_overridden(self):
        response = server.make_local_dns_response(
            dns_query("nas.nintendowifi.net"),
            "192.168.137.1",
            server.DEFAULT_DLS_HOSTS,
        )
        self.assertIsNone(response)

    def test_public_replacement_dls_hosts_are_overridden(self):
        for hostname in (
            "a.dls1.wiimmfi.de",
            "dls1.wiimmfi.de",
            "dls2.riiconnect24.net",
            "dls2.pokeacer.tk",
            "dsdl.nintendowifi.net",
        ):
            with self.subTest(hostname=hostname):
                response = server.make_local_dns_response(
                    dns_query(hostname),
                    "192.168.137.1",
                    server.DEFAULT_DLS_HOSTS,
                )
                self.assertIsNotNone(response)
                self.assertEqual(response[-4:], bytes([192, 168, 137, 1]))

    def test_unknown_dls_pattern_is_forced_local(self):
        self.assertTrue(server.is_local_distribution_name("dls9.example.net"))
        self.assertTrue(server.is_local_distribution_name("a.dls3.example.net"))
        self.assertTrue(server.is_local_distribution_name("dsdl.example.net"))
        self.assertFalse(server.is_local_distribution_name("nas.example.net"))

    def test_split_dns_uses_replacement_only_for_wfc_hosts(self):
        state = server.DnsState(
            "192.168.137.1",
            "167.235.229.36",
            "168.126.63.1",
            server.DEFAULT_DLS_HOSTS,
        )
        self.assertEqual(
            state.upstream_for("nas.nintendowifi.net"),
            ("167.235.229.36", 53),
        )
        self.assertEqual(
            state.upstream_for("chat.openai.com"),
            ("168.126.63.1", 53),
        )

    def test_dns_diagnostic_details(self):
        query = dns_query("conntest.nintendowifi.net")
        name, qtype, transaction_id = server.dns_query_details(query)
        self.assertEqual(name, "conntest.nintendowifi.net")
        self.assertEqual(qtype, 1)
        self.assertEqual(transaction_id, "1234")

        response = server.make_local_dns_response(
            query,
            "192.168.137.1",
            server.DEFAULT_DLS_HOSTS,
        )
        self.assertEqual(server.dns_response_details(response), (0, 1))

    def test_ssl3_https_serves_health_page(self):
        gift = server.GiftFile("private-gift-001.myg", bytes(server.MYG_SIZE), server.Path("test.pcd"))
        state = server.GiftState([gift], "127.0.0.1")
        https = windows_server.DSHTTPSServer(("127.0.0.1", 0), server.GiftHandler)
        https.state = state
        https.configure_tls(
            windows_server.Path("certs/server-chain.crt").resolve(),
            windows_server.Path("certs/server.key").resolve(),
        )
        thread = threading.Thread(target=https.handle_request, daemon=True)
        thread.start()
        raw = socket.create_connection(https.server_address, timeout=5)
        tls = TLSConnection(raw)
        settings = HandshakeSettings()
        settings.minVersion = (3, 0)
        settings.maxVersion = (3, 0)
        settings.versions = [(3, 0)]
        settings.useExtendedMasterSecret = False
        tls.handshakeClientCert(settings=settings)
        tls.sendall(b"GET /health HTTP/1.0\r\nHost: dls1.ilostmymind.xyz\r\n\r\n")
        response = bytearray()
        while True:
            part = tls.recv(4096)
            if not part:
                break
            response.extend(part)
        self.assertIn(b"200 OK", response)
        tls.close()
        thread.join(timeout=5)
        https.server_close()


if __name__ == "__main__":
    unittest.main()

