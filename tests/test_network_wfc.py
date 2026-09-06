from __future__ import annotations

import struct
import unittest

from configure_melonds_wfc import build_wfc_settings, melon_crc16, verify_wfc_settings
from ds_server.http_server import _is_local_client
from ds_server.network import choose_server_ip


class NetworkDetectionTests(unittest.TestCase):
    def test_prefers_active_windows_hotspot(self) -> None:
        result = choose_server_ip(["172.30.1.100", "192.168.137.1"], "172.30.1.100")
        self.assertEqual(result, "192.168.137.1")

    def test_uses_routed_address_when_hotspot_is_absent(self) -> None:
        result = choose_server_ip(["192.168.56.1", "172.30.1.100"], "172.30.1.100")
        self.assertEqual(result, "172.30.1.100")

    def test_http_client_network_filter(self) -> None:
        self.assertTrue(_is_local_client("127.0.0.1"))
        self.assertTrue(_is_local_client("192.168.137.42"))
        self.assertTrue(_is_local_client("10.0.2.15"))
        self.assertFalse(_is_local_client("87.236.176.136"))


class MelonWfcProfileTests(unittest.TestCase):
    def test_profile_has_expected_layout_and_crc(self) -> None:
        payload = build_wfc_settings("172.30.1.100")
        self.assertEqual(len(payload), 2304)
        verify_wfc_settings(payload)
        base = payload[0:0x100]
        self.assertEqual(base[0x40:0x47], b"melonAP")
        self.assertEqual(base[0xC8:0xCC], bytes((172, 30, 1, 100)))
        self.assertEqual(base[0xE7], 0)
        self.assertEqual(base[0xE8], 7)
        self.assertEqual(struct.unpack_from("<H", base, 0xFE)[0], melon_crc16(base[:0xFE]))


if __name__ == "__main__":
    unittest.main()
