import json
from datetime import datetime

from config import args
from utils import text
from utils import managers
from utils import save_data
from game_sync_server.entralinked.utility.db_manager import db

def date_to_unix(datetime_string: str):
    return datetime.strptime(datetime_string, "%Y-%m-%d").timestamp()

# ---------------------
# GET API calls
# ---------------------

def GET_item_list(_query):
    """Returns a filtered/sorted/paginated list of the player's items.

    Args:
        _query: A dict of request parameters. Possible params:
            item_kind_id: Filters the item list by category.
                0 returns all items (default).
                1 returns only berries.
            sort_key: Determines the sort order of the results.
                1 sorts by acquisition date, descending.
                2 sorts by type (bunrui_no, then b_hozon_sentou).
                3 sorts alphabetically by item name (default).
            offset: Number of items to skip for pagination.
                Defaults to 0.
            rowcount: Maximum number of items to return.
                Defaults to 9999.
            status: If set to 2, returns the list of items
                being sent to the Entralink. Defaults to 0.

    Returns:
        A JSON-encoded bytes object. 'cnt' is the total number of
        items before filtering.
    """

    item_kind_id = int(_query.get("item_kind_id", 0))
    sort_key     = int(_query.get("sort_key", 3))
    offset       = int(_query.get("offset", 0))
    rowcount     = int(_query.get("rowcount", 9999))
    status       = int(_query.get("status", 0))

    if status == 2:
        item_list = save_data.read_entralink_data()["items"]
        for item in item_list:
            item["pokeitem"] = text.lookup_str("item", item["pokeitem_id"])
        return json.dumps({"cnt": len(item_list), "list": item_list}).encode()

    if item_kind_id == 0:
        item_list = managers.chest.data["list"]
    elif item_kind_id == 1:
        item_list = [item for item in managers.chest.data["list"] if item["pokeitem_id"] in range(149, 213)]
    else:
        item_list = []

    if sort_key == 1:
        item_list = sorted(item_list, key=lambda x: date_to_unix(x["date"]), reverse=True)
    elif sort_key == 2:
        item_list = sorted(
            item_list,
            key=lambda x: (
                x["bunrui_no"],
                x["b_hozon_sentou"]
            )
        )
    elif sort_key == 3:
        item_list = sorted(item_list, key=lambda x: x["pokeitem"])

    item_list = item_list[offset:offset+rowcount]

    return json.dumps({"cnt": len(managers.chest.data["list"]), "list": item_list}).encode()


def _share_state():
    state = save_data.read_entralink_data()
    state.setdefault("share_shelf", [])
    return state


def _share_entry(item_id, x, y, material_id):
    item_desc = text.lookup_str("item_descriptions", item_id)
    return {
        "material_id": material_id,
        "item_id": item_id,
        "pokeitem": text.lookup_str("item", item_id),
        "x": x,
        "y": y,
        "history_id": None,
        "old_member_savedata_id": None,
        "pokemon_no": None,
        "form_no": None,
        "pokename": None,
        "pgl_name": None,
        "nickname": None,
        "poke_nickname": None,
        "field_line1": item_desc[0],
        "field_line2": item_desc[1],
        "field_line3": item_desc[2],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "old_item_id": None,
        "new_item_id": None,
        "old_item_name": None,
    }


def GET_item_trade_list(_query):
    return json.dumps(_share_state()["share_shelf"]).encode()


def GET_friend_trade_list(_query):
    # This local single-player revival exposes the same shelf for Dream Pal mode.
    return GET_item_trade_list(_query)


def GET_item_exhibit_update(query):
    item_id = int(query["item_id"])
    x, y = int(query["x"]), int(query["y"])
    if not (1 <= x <= 3 and 1 <= y <= 3):
        raise ValueError("선반 위치는 1~3 범위여야 합니다.")
    state = _share_state()
    shelf = state["share_shelf"]
    if any(int(item["x"]) == x and int(item["y"]) == y for item in shelf):
        raise ValueError("That Share Shelf position is already occupied")
    managers.chest.remove_item(item_id, 1)
    material_id = max((int(item["material_id"]) for item in shelf), default=0) + 1
    entry = _share_entry(item_id, x, y, material_id)
    shelf.append(entry)
    db.write(save_data.gscd, "game_sync", state)
    return json.dumps([entry]).encode()


def GET_item_return_update(query):
    material_id = int(query["material_id"])
    state = _share_state()
    shelf = state["share_shelf"]
    entry = next((item for item in shelf if int(item["material_id"]) == material_id), None)
    if entry is None:
        raise ValueError(f"Unknown Share Shelf material: {material_id}")
    managers.chest.add_item(int(entry["item_id"]), 1)
    state["share_shelf"] = [item for item in shelf if int(item["material_id"]) != material_id]
    db.write(save_data.gscd, "game_sync", state)
    return b"{}"


def GET_item_trade_update(query):
    new_item_id = int(query["item_id"])
    material_id = int(query["other_material_id"])
    state = _share_state()
    shelf = state["share_shelf"]
    old = next((item for item in shelf if int(item["material_id"]) == material_id), None)
    if old is None:
        raise ValueError(f"Unknown Share Shelf material: {material_id}")
    managers.chest.remove_item(new_item_id, 1)
    managers.chest.add_item(int(old["item_id"]), 1)
    replacement = _share_entry(new_item_id, int(old["x"]), int(old["y"]), material_id)
    replacement.update({
        "history_id": int(datetime.now().timestamp()),
        "old_item_id": old["item_id"],
        "new_item_id": new_item_id,
        "old_item_name": old["pokeitem"],
        "old_member_savedata_id": save_data.read_player_data()["member"].get("member_savedata_id"),
    })
    state["share_shelf"] = [replacement if int(item["material_id"]) == material_id else item for item in shelf]
    db.write(save_data.gscd, "game_sync", state)
    return json.dumps([replacement]).encode()

# ---------------------
# POST API calls
# ---------------------

def POST_item_delivery_update(_query):
    print(json.dumps(_query, indent=2))

    # Build the new queue from the request
    new_queue = {}
    for k, item_pair in _query.items():
        if not k.startswith("item_id"):
            continue
        item_id, item_count = item_pair.split("_")
        item_id, item_count = int(item_id), int(item_count)
        if str(item_id) not in managers.item_info or not 1 <= item_count <= 255:
            raise ValueError("전송할 아이템과 수량을 확인하세요.")
        new_queue[item_id] = item_count
    if len(new_queue) > 20:
        raise ValueError("아이템은 최대 20종류까지 전송할 수 있습니다.")

    # Build the old queue from whatever is currently staged
    old_queue = {
        item["pokeitem_id"]: item["item_cnt"]
        for item in save_data.read_entralink_data().get("items", [])
    }

    # Determine the delta to add/subtract Chest items
    all_ids = set(new_queue) | set(old_queue)
    # Validate the entire request before charging any inventory.
    for item_id in all_ids:
        delta = new_queue.get(item_id, 0) - old_queue.get(item_id, 0)
        item = managers.chest.fetch_item_by_id(item_id)
        if delta > 0 and (item is None or item["item_cnt"] < delta):
            raise ValueError("전송할 아이템 수량이 부족합니다.")
    for item_id in all_ids:
        delta = new_queue.get(item_id, 0) - old_queue.get(item_id, 0)
        if delta > 0:
            managers.chest.remove_item(item_id, delta)
        elif delta < 0:
            managers.chest.add_item(item_id, -delta)

    # Save the new queue state
    item_list = [
        {"pokeitem_id": item_id, "item_cnt": item_cnt}
        for item_id, item_cnt in new_queue.items()
    ]

    if args.game_sync:
        save_data.write_entralink_data(item_list, "items")

    return b'{}'


