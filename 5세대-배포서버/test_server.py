import tempfile
import unittest
from pathlib import Path

import server


class Gen5GiftTests(unittest.TestCase):
    def test_pgf_to_wire_layout_and_checksum(self):
        pgf = bytes(range(204))
        wire = server.pgf_to_wire(pgf, language=8, game_flags=0xF0, message="테스트")
        self.assertEqual(len(wire), 720)
        self.assertEqual(wire[:204], pgf)
        self.assertEqual(wire[0xCE:0xD0], b"\xF0\x00")
        self.assertEqual(wire[0x2CB], 8)
        self.assertEqual(int.from_bytes(wire[-2:], "little"), server.crc16_ccitt(wire[:-2]))

    def test_directory_rejects_wrong_size(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "bad.pgf").write_bytes(b"bad")
            with self.assertRaisesRegex(ValueError, "bad.pgf"):
                server.load_gift_directory(Path(folder))

    def test_directory_rejects_out_of_range_card_id(self):
        with tempfile.TemporaryDirectory() as folder:
            data = bytearray(204)
            data[0xB0:0xB2] = (2048).to_bytes(2, "little")
            Path(folder, "bad-card-id.pgf").write_bytes(data)
            with self.assertRaisesRegex(ValueError, "card ID must be 1-2047"):
                server.load_gift_directory(Path(folder))

    def test_directory_rejects_non_receivable_card_status(self):
        with tempfile.TemporaryDirectory() as folder:
            data = bytearray(204)
            data[0xB0:0xB2] = (1).to_bytes(2, "little")
            data[0xB3] = 1
            data[0xB4] = 0
            Path(folder, "repeatable.pgf").write_bytes(data)
            with self.assertRaisesRegex(ValueError, "card status must be 1"):
                server.load_gift_directory(Path(folder))

    def test_request_filters_korean_all_games(self):
        self.assertEqual(server.request_filters({"attr1": "MYSTERY_K", "rhgamecd": "IREK"}), (8, 0x80))

    def test_directory_loads_exact_wc5full_without_repacking(self):
        pgf = bytearray(204)
        pgf[0xB0:0xB2] = (37).to_bytes(2, "little")
        pgf[0xB3] = 1
        pgf[0xB4] = 1
        wire = server.pgf_to_wire(bytes(pgf), language=8, game_flags=0x30)
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "control.wc5full").write_bytes(wire)
            gift = server.load_gift_directory(Path(folder))[0]
            self.assertEqual(gift.myg, wire)
            self.assertEqual((gift.language, gift.game_flags), (8, 0xF0))

    def test_attached_gift_loads_as_korean_all_games(self):
        gift_dir = Path(__file__).parent / "배포파일"
        gifts = server.load_gift_directory(gift_dir)
        self.assertEqual(len(gifts), 1)
        self.assertIn(gifts[0].source.suffix.lower(), {".pgf", ".wc5full"})
        self.assertEqual((gifts[0].language, gifts[0].game_flags), (8, 0xF0))
        self.assertEqual(len(gifts[0].myg), 720)


if __name__ == "__main__":
    unittest.main()

