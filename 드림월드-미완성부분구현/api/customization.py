"""Select only locally installed DLC names understood by the Game Sync server."""
from pathlib import Path
from utils import save_data
from game_sync_server.entralinked.utility.db_manager import db

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {"cgear": "cgear_skin", "pokedex": "dex_skin", "musical": "musical"}


def options():
    member = save_data.read_player_data().get("member", {})
    cgear_type = "CGEAR2" if member.get("rom_id") in (22, 23) else "CGEAR"
    base = ROOT / "game_sync_server" / "dlc"
    if not base.exists():
        base = ROOT / "game_sync_server/entralinked/data/dlc_skins"
    result = {}
    for field, kind in (("cgear", cgear_type), ("pokedex", "ZUKAN"), ("musical", "MUSICAL")):
        folder = base / "IRAO" / kind
        result[field] = sorted(path.name for path in folder.iterdir() if path.is_file() and path.name not in ("none", "custom")) if folder.is_dir() else []
    return result


def current():
    state = save_data.read_entralink_data()
    return {field: state.get(key) for field, key in FIELDS.items()}


def select(values):
    if not save_data.read_player_data().get("member"):
        raise ValueError("게임싱크 계정을 먼저 등록하세요.")
    available = options()
    state = save_data.read_entralink_data()
    changes = {}
    for field, key in FIELDS.items():
        if field not in values:
            continue
        name = values[field] or None
        if name is not None and name not in available[field]:
            raise ValueError("현재 게임에 사용할 수 없는 다운로드 콘텐츠입니다.")
        changes[key] = name
    state.update(changes)
    db.write(save_data.gscd, "game_sync", state)
