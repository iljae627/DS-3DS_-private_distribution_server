import json
import os
import tempfile
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEST_GSCD = "CODEX-PDW-FEATURES"


class MissingFeatureFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pdw-features-")
        self.addCleanup(self.temp.cleanup)
        self.env = {**os.environ, "PDW_SAVE_DIR": self.temp.name}

    def test_friend_board_transfer_shelf_and_catalogue(self):
        save_dir = Path(self.temp.name)
        save_dir.mkdir(exist_ok=True)
        gscd_file = save_dir / "gscd.txt"
        old_gscd = gscd_file.read_bytes() if gscd_file.exists() else None

        setup = f"""
from game_sync_server.entralinked.utility.db_manager import db
db.write_gscd({TEST_GSCD!r})
db.write({TEST_GSCD!r}, 'player_data', {{'member': {{
    'langcode': 8, 'rom_id': 21, 'experiment_point': 0,
    'player_badge_num': 8, 'type1': 11, 'type2': 3, 'world_id': 1,
    'shelf_id': 301, 'island_id': 201, 'play_status': 2,
    'gscd': {TEST_GSCD!r}, 'gsid': 1, 'player_name': 'CODEX',
    'country_id': 176, 'member_id': 3000001,
}}}})
db.write({TEST_GSCD!r}, 'game_sync', {{
    'levels_gained': 0, 'hours_played': 0, 'minutes_played': 0,
    'cgear_skin': None, 'dex_skin': None, 'musical': None,
    'custom_cgear_skin': None, 'custom_dex_skin': None, 'custom_musical': None,
    'encounters': [], 'items': [], 'avenue_visitors': [], 'decor': [],
    'loblolly_decor': None,
}})
db.write({TEST_GSCD!r}, 'sleeping_pokemon', {{
    'pokemon_no': 25, 'form_no': 0, 'type1': 13, 'type2': 0,
    'pokemon_nickname': 'PIKACHU', 'oyaname': 'CODEX', 'level': 10,
    'sex': 0, 'personality': 0, 'ball_name': 4,
    'trainer_id': 1, 'trainer_secret_id': 2,
}})
db.close()
"""
        subprocess.run([sys.executable, "-c", setup], cwd=ROOT, env=self.env, check=True)
        gscd_file.write_text(TEST_GSCD, encoding="utf-8")

        probe = r'''
import sys
import io
import hashlib
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'game_sync_server'))
sys.path.insert(0, str(Path.cwd() / 'game_sync_server' / 'entralinked'))
from api.server import app
from model.player.player import Player
from network.http.pgl_handler import PglHandler
from utility.le_input_output import LEOutputStream
from game_sync_server.entralinked.utility.db_manager import db
from utils import save_data

client = app.test_client()
top = client.get('/api/?p=pdw.dreamland.top').get_json()
pokemon = next(entry for entry in top['object_list'] if entry['object_category'] != 2)
pid = pokemon['object_pokemon_id']

cleared = client.post('/api/?p=pdw.dreamland.game_clear', data={
    'object_pokemon_id': str(pid), 'pokeitem_id': '0', 'result': hashlib.md5(f"1{pokemon['otoken']}{pid}".encode()).hexdigest()
})
assert cleared.status_code == 200, cleared.get_data(as_text=True)
tree = client.get('/api/?p=pdw.dreamland.tree_top').get_json()
assert any(p['get_pokemon_id'] == pid for p in tree['encount_list'])

offered = client.post('/api/?p=pdw.dreamland.tree_offer', data={
    'get_pokemon_id': str(pid), 'pokeitem_id': '149'
})
assert offered.status_code == 200, offered.get_data(as_text=True)
board = client.get('/api/?p=pdw.home.board_pokemon_list&status_type=1&offset=0&rowcount=10').get_json()
assert board['total_count'] == 1

selected = client.post('/api/?p=pdw.home.board_pokemon_selects', data={
    'get_pokemon_id[0]': str(pid)
})
assert selected.status_code == 200
state = save_data.read_entralink_data()
assert state['selected_friend_ids'] == [pid]
assert len(state['encounters']) == 1
assert 'get_pokemon_id' not in state['encounters'][0]
player = Player.from_dict(save_data.read_player_data(), state, None)
_, serialized_state, _ = player.to_dict()
assert serialized_state['friend_board'][0]['get_pokemon_id'] == pid
assert isinstance(serialized_state['encounters'][0]['animation'], int)
binary = io.BytesIO()
PglHandler._write_encounters(None, LEOutputStream(binary), player.encounters)
assert len(binary.getvalue()) == 80
selected_board = client.get('/api/?p=pdw.home.board_pokemon_list&status_type=2&offset=0&rowcount=10').get_json()
assert selected_board['total_count'] == 1
assert selected_board['pokemon_list'][0]['is_selected'] == 1

exhibit = client.get('/api/?p=pdw.item.item_exhibit_update&item_id=150&x=1&y=2')
assert exhibit.status_code == 200
shelf = client.get('/api/?p=pdw.item.item_trade_list').get_json()
assert len(shelf) == 1
material_id = shelf[0]['material_id']
traded = client.get(
    f'/api/?p=pdw.item.item_trade_update&item_id=151&other_member_id=1&other_material_id={material_id}'
).get_json()
assert traded[0]['old_item_id'] == 150
assert traded[0]['new_item_id'] == 151
friend_shelf = client.get('/api/?p=pdw.item.friend_trade_list').get_json()
assert friend_shelf[0]['item_id'] == 151
returned = client.get(
    f'/api/?p=pdw.item.item_return_update&material_id={material_id}&x=1&y=2'
)
assert returned.status_code == 200
assert client.get('/api/?p=pdw.item.item_trade_list').get_json() == []

catalog = client.get('/api/?p=pdw.interior.interior_list').get_json()
assert any(item['interior_id'] == 202 for item in catalog)
bought = client.post('/api/?p=pdw.interior.my_interior_insert', data={'interior_id': '202'}).get_json()
my_id = bought[0]['my_interior_id']
assert client.get(f'/api/?p=pdw.interior.interior_change_update&my_interior_id={my_id}').status_code == 200
layout = client.post('/api/?p=pdw.interior.interior_layout_update', data={
    'interior[0]': '-1_10_20_1', 'interior[1]': '-2_0_0_0'
})
assert layout.status_code == 200
assert save_data.read_entralink_data()['interior_layout'][0]['x'] == 10
island = client.get('/api/?p=pdw.home.my_island').get_json()
assert island['arranged_interior_list'][0]['my_interior_id'] == -1
assert island['island_id'] == 202
catalog_again = client.get('/api/?p=pdw.interior.interior_list').get_json()
owned = next(item for item in catalog_again if item['interior_id'] == 202)
assert owned['my_interior_id'] == my_id

player.reset_dream_info()
awake_player_data, awake_state, awake_sleeper = player.to_dict()
assert awake_player_data['member']['play_status'] == 0
assert awake_player_data['member']['sleeping_flag'] == 0
assert awake_player_data['member']['isin_sleep_pokemon'] == 0
assert awake_sleeper is None

thumb = client.get('/src/swf/theme/assets/global/parts/interior/202thumb.swf')
assert thumb.status_code == 200
print('all feature flows passed')
'''

        try:
            completed = subprocess.run(
                [sys.executable, "-c", probe], cwd=ROOT,
                text=True, capture_output=True,
                env=self.env,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
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
