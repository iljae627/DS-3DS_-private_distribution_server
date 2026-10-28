"""Contracts taken from recovered Connection.as / JSONLoader.as and SWF loaders."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SETUP = r'''
import sys, json, hashlib, time
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'game_sync_server'))
sys.path.insert(0, str(Path.cwd() / 'game_sync_server' / 'entralinked'))
from game_sync_server.entralinked.utility.db_manager import db
from model.player.player import Player
gscd='WEB-CONTRACT'
db.write_gscd(gscd)
p=Player._empty_player_data()
p['member'].update({'gscd':gscd,'langcode':8,'rom_id':21,'gsid':1,'player_name':'TEST','pgl_name':'TEST','pokemon_no':25,'form_no':0,'type1':13,'type2':None,'player_badge_num':8,'world_id':1,'play_status':1,'member_savedata_id':1})
db.write(gscd,'player_data',p)
db.write(gscd,'game_sync',{'levels_gained':0,'hours_played':0,'minutes_played':0,'encounters':[],'items':[],'decor':[],'avenue_visitors':[]})
db.write(gscd,'sleeping_pokemon',{'pokemon_no':25,'form_no':0,'type1':13,'type2':None,'pokemon_nickname':'TEST','oyaname':'TEST','level':10,'sex':0,'personality':0,'ball_name':4,'trainer_id':1,'trainer_secret_id':2})
(Path(os.environ['PDW_SAVE_DIR'])/'gscd.txt').write_text(gscd)
from api.server import app
from utils import managers, save_data
managers.chest.update_json()
client=app.test_client()
def post(name, **data):
    return client.post('/api/',data={'p':name,'token':'',**data})
def get(name, **data):
    return client.get('/api/',query_string={'p':name,**data})
def count(item_id):
    entry=managers.chest.fetch_item_by_id(item_id)
    return entry['item_cnt'] if entry else 0
'''


class WebContractTest(unittest.TestCase):
    def run_probe(self, body):
        with tempfile.TemporaryDirectory(prefix="pdw-contract-") as folder:
            result = subprocess.run([sys.executable, "-c", "import os\n" + SETUP + body], cwd=ROOT,
                                    env={**os.environ, "PDW_SAVE_DIR":folder}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_flash_methods_assets_and_error_contract(self):
        self.run_probe(r'''
for name in ('pdw.interior.interior_catalog_list','pdw.interior.interior_list','pdw.item.item_trade_list'):
    r=post(name)
    assert r.status_code==200 and isinstance(r.get_json(),list),(name,r.data)
for path in ('/','/pdw/','/profile/','/support/','/report/','/local/','/crossdomain.xml','/src/swf/theme/assets/global/parts/interior/301.swf','/src/swf/theme/assets/global/parts/interior/catalogimg_1.swf','/src/swf/theme/assets/global/parts/interior/202_2.swf','/src/swf/theme/assets/global/parts/interior/202_3.swf','/src/swf/theme/assets/global/parts/interior/202_4.swf'):
    assert client.get(path,follow_redirects=True).status_code==200,path
assert client.get('/ja.pokemon-gl.com/profile/',follow_redirects=True).status_code==200
assert post('pgl.member.profile.avator_select',avator_id='4').get_json()=={}
assert save_data.read_player_data()['member']['avator_id']==4
assert get('pgl.member.profile.my_pdw_profile_by_pgl').status_code==200
assert get('pgl.top.init').status_code==200
bad=post('pdw.interior.my_interior_insert',interior_id='999999')
assert bad.status_code==400 and 'details' in bad.get_json()['error']
assert client.get('/api/?p=hb&token=&ignored').status_code==200
assert client.get('/missing-does-not-exist.swf').status_code==404
assert client.get('/%2e%2e/config.py').status_code==404
''')

    def test_real_result_hash_failure_replay_and_restart(self):
        self.run_probe(r'''
top=get('pdw.dreamland.top').get_json()
entry=top['object_list'][0]
pid=entry['object_pokemon_id']
form={'object_pokemon_id':str(pid),'pokeitem_id':'0','result':hashlib.md5(f"1{entry['otoken']}{pid}".encode()).hexdigest()}
from api import pdw_dreamland
pdw_dreamland.encounter_store.clear() # emulate memory loss / server restart
first=post('pdw.dreamland.game_clear',**form)
assert first.status_code==200,first.data
points=save_data.read_player_data()['member']['experiment_point']
assert post('pdw.dreamland.game_clear',**form).get_json()==first.get_json()
assert save_data.read_player_data()['member']['experiment_point']==points
assert len(save_data.read_entralink_data()['befriended'])==1
new=get('pdw.dreamland.top').get_json()['object_list'][0]
assert new['object_pokemon_id']!=pid
failed=post('pdw.dreamland.game_clear',object_pokemon_id=str(new['object_pokemon_id']),pokeitem_id='0',result=hashlib.md5(f"0{new['otoken']}{new['object_pokemon_id']}".encode()).hexdigest())
assert failed.status_code==200 and failed.get_json()['pokemon'] is None
assert len(save_data.read_entralink_data()['befriended'])==1
''')

    def test_customization_queues_installed_dlc(self):
        self.run_probe(r'''
choices=get('pgl.member.profile.customize').get_json()
assert choices['cgear'] and choices['pokedex'] and choices['musical']
selected={key:choices[key][0] for key in ('cgear','pokedex','musical')}
assert post('pgl.member.profile.customize',**selected).status_code==200
state=save_data.read_entralink_data()
assert state['cgear_skin']==selected['cgear']
assert state['dex_skin']==selected['pokedex']
assert state['musical']==selected['musical']
from model.dlc.dlc import DlcList
dlc=DlcList()
for field,kind in (('cgear','CGEAR'),('pokedex','ZUKAN'),('musical','MUSICAL')):
    assert dlc.get_dlc_index('IRAO',kind,selected[field])>0
assert client.get('/customize/',follow_redirects=True).status_code==200
assert client.post('/local/customize',data=selected).status_code==303
assert post('pgl.member.profile.customize',cgear='../config.json').status_code==400
assert save_data.read_entralink_data()['cgear_skin']==selected['cgear']
''')

    def test_inventory_and_garden_persistence(self):
        self.run_probe(r'''
original=count(149)
assert post('pdw.croft.kinomi_sowing',my_croft_id='1000',pokeitem_id='149').status_code==200
assert count(149)==original-1
assert post('pdw.croft.kinomi_sowing',my_croft_id='1000',pokeitem_id='149').status_code==400
assert count(149)==original-1
assert post('pdw.croft.kinomi_harvesting',my_croft_id='1000').status_code==400
plot=managers.crops.fetch_plot_by_id(1000)
plot['server']['planted_at']=int(time.time())-200*3600
plot['server']['updated_at']=plot['server']['planted_at']
grown=get('pdw.croft.my_croft_list').get_json()
assert grown['croft_list'][0]['kinomi_state']==4
assert post('pdw.croft.kinomi_harvesting',my_croft_id='1000').status_code==200
save_data.write_player_data({'experiment_point':2200})
expanded=get('pdw.croft.my_croft_list').get_json()
assert len(expanded['croft_list'])==12
assert len(db.read(gscd,'crop_data')['croft_list'])==12
before=count(150)
bad=post('pdw.item.item_delivery_update',**{'item_id[0]':'150_1','item_id[1]':'151_255'})
assert bad.status_code==400 and count(150)==before
assert post('pdw.item.item_delivery_update',**{'item_id[0]':'150_2'}).status_code==200
assert count(150)==before-2
assert save_data.read_entralink_data()['items']==[{'pokeitem_id':150,'item_cnt':2}]
assert post('pdw.item.item_delivery_update').status_code==200
assert count(150)==before
''')


if __name__ == "__main__":
    unittest.main()
