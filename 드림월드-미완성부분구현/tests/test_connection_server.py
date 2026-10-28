import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRALINKED = ROOT / "game_sync_server" / "entralinked"
sys.path.insert(0, str(ROOT / "game_sync_server"))
sys.path.insert(0, str(ENTRALINKED))

from configuration import Configuration
from network.http.http_server import HttpServer


class _Context:
    configuration = Configuration()
    user_manager = object()
    player_manager = object()
    dlc_list = object()


class ConnectionServerTest(unittest.TestCase):
    def test_nintendo_connection_test_response(self):
        server = HttpServer(_Context())
        response = server.app.test_client().get(
            "/",
            headers={"Host": "conntest.nintendowifi.net"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Organization"], "Nintendo")
        self.assertIn(b"This is test.html page", response.data)


if __name__ == "__main__":
    unittest.main()
