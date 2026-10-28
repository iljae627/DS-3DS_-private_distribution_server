import tempfile
import unittest
from pathlib import Path

import server


class Gen6Tests(unittest.TestCase):
    def test_load_and_npfl(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "sample.wc6"
            data = bytearray(server.WC6_SIZE)
            data[:2] = (1004).to_bytes(2, "little")
            data[2:8] = "테스트".encode("utf-16le")
            p.write_bytes(data)
            gift = server.load_gifts(Path(tmp))[0]
            self.assertEqual(gift.card_id, 1004)
            self.assertEqual(gift.wire_name, "1004_PrivateGift_KO_K")
            result = server.make_filelist(gift)
            self.assertIn(b"\t\tMYS_KO_K\tF\tN\t", result)
            self.assertNotIn(b"MYS_KR_K", result)
            first, rest = result.split(b"\r\n", 1)
            self.assertEqual(first, __import__("hashlib").sha1(rest).hexdigest().encode())
            self.assertEqual(int(rest.split(b"\r\n", 1)[0]), len(result))
            fields = rest.split(b"\r\n", 2)[1].split(b"\t")
            self.assertEqual(fields[1:5], [b"", b"MYS_KO_K", b"F", b"N"])

            full = server.make_wc6full(gift, 1)
            self.assertEqual(len(full), server.WC6FULL_SIZE)
            self.assertEqual(full[0], 1)
            self.assertEqual(full[0x1FF], server.KOREAN_LANGUAGE)
            self.assertEqual(full[0x205:0x208], b"FFF")
            self.assertEqual(full[0x208:], data)

    def test_key_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "aes_keys.txt"
            p.write_text("slot0x38KeyN=" + "12" * 16, encoding="utf-8")
            self.assertEqual(server.load_boss_key(p), bytes.fromhex("12" * 16))

    def test_wrong_wc6_size_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "bad.wc6").write_bytes(b"bad")
            with self.assertRaises(ValueError):
                server.load_gifts(Path(tmp))

    def test_korean_oras_network_beldum_wire_name(self):
        path = server.ROOT / "배포파일" / "Card # 1504 - 색이 다른 은색 메탕.wc6"
        gift = server.load_gifts(path.parent)
        beldum = next(item for item in gift if item.path == path)
        self.assertEqual(beldum.card_id, 1504)
        self.assertEqual(beldum.wire_name, "1504_Steven_Shiny_Beldum_KO_K")
        self.assertIsNotNone(beldum.full_data)
        self.assertEqual(server.make_wc6full(beldum, 0x08), beldum.full_data)
        self.assertEqual(beldum.full_data[0], 0x0C)  # Omega Ruby + Alpha Sapphire
        self.assertEqual(beldum.full_data[0x208:], beldum.data)

    def test_official_signed_boss_diagnostic(self):
        directory = server.ROOT / "배포파일"
        potion = next(item for item in server.load_gifts(directory) if item.card_id == 1022)
        self.assertEqual(potion.wire_name, "1022_DubblePack_Kizugusuri_KO")
        self.assertIsNotNone(potion.full_data)
        self.assertIsNotNone(potion.boss_data)
        self.assertEqual(potion.boss_data[:4], b"boss")
        self.assertEqual(len(potion.full_data), server.WC6FULL_SIZE)
        self.assertEqual(potion.full_data[0x208:], potion.data)

    def test_conntest_is_local(self):
        self.assertIn("conntest.nintendowifi.net", server.LOCAL_HOSTS)
        self.assertIn(b"This is test.html page", server.CONNTEST_BODY)

    def test_nppl_policy_is_local_and_valid(self):
        self.assertIn("nppl.c.app.nintendowifi.net", server.LOCAL_HOSTS)
        body = server.make_policylist()
        self.assertIn(b"<MajorVersion>3</MajorVersion>", body)
        self.assertIn(b"<DefaultStop>false</DefaultStop>", body)
        self.assertEqual(body.count(b"<Priority>"), 6)
        self.assertIn(b"<Persistent>true</Persistent>", body)


if __name__ == "__main__":
    unittest.main()
