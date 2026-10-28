import json
from zoneinfo import ZoneInfo
from datetime import datetime
from random import choice, randint

from utils import text
from utils import pokemon
from utils import save_data
from game_sync_server.entralinked.utility.db_manager import db

# ---------------------
# GET API calls
# ---------------------

def _load_sleeping_pokemon():
    """Return the localized sleeping Pokémon, restoring the web cache if needed."""
    stored = db.read(save_data.gscd, "sleeping_pokemon")
    if not stored:
        pokemon.sleeper = None
        return {}

    pokemon.sleeper = {
        "pokemon_no": stored["pokemon_no"],
        "pokemon_name": text.lookup_str("pokemon", stored["pokemon_no"]),
        "form_no": stored["form_no"],
        "type1": text.lookup_str("type", stored["type1"]),
        "type2": text.lookup_str("type", stored["type2"]),
        "pokemon_nickname": stored["pokemon_nickname"],
        "oyaname": stored["oyaname"],
        "level": stored["level"],
        "sex": stored["sex"],
        "personality": text.lookup_str("nature", stored["personality"]),
        "ball_name": text.lookup_str("ball", stored["ball_name"]),
    }
    return pokemon.sleeper

def GET_board_pokemon_list(_query):
    game_sync = save_data.read_entralink_data()
    pokemon_list = game_sync.get("friend_board", [])
    status_type = int(_query.get("status_type", 1))
    selected_ids = {int(value) for value in game_sync.get("selected_friend_ids", [])}
    if status_type == 2:
        pokemon_list = [p for p in pokemon_list if int(p["get_pokemon_id"]) in selected_ids]
    offset = int(_query.get("offset", 0))
    rowcount = int(_query.get("rowcount", 10))
    response_list = []
    for pokemon_entry in pokemon_list[offset:offset + rowcount]:
        item = dict(pokemon_entry)
        item["is_selected"] = int(int(item["get_pokemon_id"]) in selected_ids)
        response_list.append(item)
    return json.dumps({"total_count": len(pokemon_list), "pokemon_list": response_list}).encode()


def POST_board_pokemon_selects(query):
    values = [
        int(value)
        for key, value in sorted(query.items(), key=lambda pair: int(pair[0].split("[")[1].rstrip("]")) if pair[0].startswith("get_pokemon_id[") else -1)
        if key.startswith("get_pokemon_id[")
    ][:10]
    game_sync = save_data.read_entralink_data()
    board = game_sync.get("friend_board", [])
    valid_ids = {int(entry["get_pokemon_id"]) for entry in board}
    if len(values) != len(set(values)) or any(value not in valid_ids for value in values):
        raise ValueError("친구보드에서 전송할 포켓몬을 다시 선택하세요.")
    selected = []
    for entry in board:
        if int(entry["get_pokemon_id"]) not in values:
            continue
        selected.append({
            "species": int(entry["pokemon_no"]),
            "move": int(entry.get("move_id", 0)),
            "form": int(entry.get("form_no", 0)),
            "gender": int(entry.get("sex_id", 0)),
            "animation": int(entry.get("animation", 0)),
        })
    game_sync["encounters"] = selected
    game_sync["selected_friend_ids"] = values
    db.write(save_data.gscd, "game_sync", game_sync)
    return b"{}"


def GET_footprint_list(_query):
    # The archive's generated visitors pointed to nonexistent islands.
    return json.dumps({"list": []}).encode()


def _demo_footprint_list(_query):
    footprint_list = {"list":[]}

    # This is an arbitrary subset of "interesting" (non-empty) footprints
    valid_footprints = [598,25,85,623,2,32,183,428,648,636,616,609,594,593,574,564,558,547,543,520,518,491,474,421,420,406,121,120,13,10,647]

    for _ in range(10):
        pkmn = pokemon.get_random_pokemon(valid_footprints)
        footprint = {
            "is_pdw": randint(0, 1),
            "is_gts": randint(0, 1),
            "is_ds": randint(0, 1),
            "friend_type": randint(0, 2),
            "updated_at": "2026/05/06 22:00",
            "pokemon_nickname": "pokemon_nickname",
            "pokemon_name": text.lookup_str("pokemon", pkmn["pokemon_no"]),
            "pgl_name": "pgl_name",
            "pokemon_no": pkmn["pokemon_no"],
            "form_no": pkmn.get("form_no", 0), #below this is used for the popup menu
            "oyaname": "oyaname",
            "level": pkmn["level"],
            "type1": text.lookup_str("type", pkmn["type1"]),
            "type2": text.lookup_str("type", pkmn["type2"]),
            "sex_id": choice(pkmn["gender_ratio"]),
            "personality": text.lookup_str("nature", randint(0, 24)),
            "exchange_flag": randint(0, 1),
            "water_flag": randint(0, 1)
        }
        footprint_list["list"].append(footprint)

    return json.dumps(footprint_list).encode()


def GET_my_bridge(_query):
    return b'{}'


def GET_friend_list(_query):
    return json.dumps({"friend_list": [], "list": [], "total_count": 0, "cnt": 0}).encode()


def GET_campaign_island_list(_query):
    return b'{"campaign_island_list":[]}'


def GET_friend_island(query):
    member = save_data.read_player_data().get("member", {})
    target = query.get("other_member_savedata_id", query.get("member_savedata_id"))
    if target is not None and str(target) == str(member.get("member_savedata_id")):
        return GET_my_island(query)
    raise ValueError("현재 로컬 서버에는 방문 가능한 드림친구가 없습니다.")


def GET_my_island(_query):
    pkmn = _load_sleeping_pokemon()
    member = save_data.read_player_data().get("member", {})
    from api.pdw_interior import arranged_interiors

    response = {
        "pokemon":                 {**pkmn},
        "island_id":               member.get("island_id", 201),
        "point":                   member.get("experiment_point", 0),
        "trial_flag":              0,
        "arranged_interior_list":  arranged_interiors(),
        "requested_flag":          False,
        "shelf_id":                member.get("shelf_id", 301)
    }
    return json.dumps(response).encode()


def GET_my_island_area(_query):
    player_data = save_data.read_player_data()

    # Do not advertise random nonexistent players whose islands have no API.
    friend_list = []
    response = {
        "island_id": player_data["member"]["island_id"],
        "friend_list": friend_list
    }

    return(json.dumps(response).encode())


def GET_pdw_end(_query):
    save_data.update_gamesync_status(save_data.PlayerStatus.WAKE_READY)

    return b'{}'

# ---------------------
# POST API calls
# ---------------------

def POST_pdw_start(_query):
    if not db.read(save_data.gscd, "sleeping_pokemon"):
        raise ValueError("게임에서 포켓몬을 재운 뒤 드림월드에 입장하세요.")
    now_local = datetime.now().astimezone()
    now_japan = now_local.astimezone(ZoneInfo("Asia/Tokyo"))

    pokemon_no = save_data.read_player_data()["member"]["pokemon_no"]

    data = {
        "last_started_at": int(now_japan.timestamp()),
        "last_logined_at": int(now_japan.timestamp()),
        "last_started_at_timezone": int(now_local.timestamp()),
        "pokemon_name": text.lookup_str("pokemon", pokemon_no)
    }

    save_data.write_player_data(data)

    _load_sleeping_pokemon()

    response = {"started_at":int(now_local.timestamp())}
    return json.dumps(response).encode()


def POST_pdw_timecheck(_query):
    return b'{}'
