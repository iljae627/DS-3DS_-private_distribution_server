import json
import os
import tempfile
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST_GSCD = "CODEX-PDW-SMOKE"


class PdwSmokeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pdw-smoke-")
        self.addCleanup(self.temp.cleanup)
        self.env = {**os.environ, "PDW_SAVE_DIR": self.temp.name}

    def test_korean_bw_dream_island_and_static_site(self):
        """Exercise the PDW route with the Korean locale and a BW ROM ID."""
        save_dir = Path(self.temp.name)
        save_dir.mkdir(exist_ok=True)
        gscd_file = save_dir / "gscd.txt"
        old_gscd = gscd_file.read_bytes() if gscd_file.exists() else None

        setup = f"""
from game_sync_server.entralinked.utility.db_manager import db
db.write_gscd({TEST_GSCD!r})
db.write({TEST_GSCD!r}, 'player_data', {{'member': {{
    'langcode': 8, 'rom_id': 21, 'experiment_point': 0,
    'player_badge_num': 8, 'type1': 11, 'type2': 3, 'world_id': 1
}}}})
db.close()
"""
        subprocess.run([sys.executable, "-c", setup], cwd=ROOT, env=self.env, check=True)
        gscd_file.write_text(TEST_GSCD, encoding="utf-8")

        probe = """
import json
from api.server import app
client = app.test_client()
root = client.get('/')
assert root.status_code == 200, root.status_code
response = client.get('/api/?p=pdw.dreamland.top')
assert response.status_code == 200, response.get_data(as_text=True)
payload = response.get_json()
assert payload['dreamland_area_id']
assert len(payload['object_list']) == 30
print(json.dumps({'root': root.status_code, 'area': payload['dreamland_area_id'], 'objects': len(payload['object_list'])}))
"""

        try:
            completed = subprocess.run(
                [sys.executable, "-c", probe], cwd=ROOT,
                text=True, capture_output=True,
                env=self.env,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout.strip().splitlines()[-1])
            self.assertEqual(result["root"], 200)
            self.assertEqual(result["objects"], 30)
        finally:
            with sqlite3.connect(save_dir / "pokemon_saves.db") as conn:
                conn.execute("DELETE FROM player_saves WHERE gscd = ?", (TEST_GSCD,))
            conn.close()
            if old_gscd is None:
                gscd_file.unlink(missing_ok=True)
            else:
                gscd_file.write_bytes(old_gscd)


if __name__ == "__main__":
    unittest.main()
