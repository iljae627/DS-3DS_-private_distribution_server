"""Dream Catalogue and room-decoration endpoints used by the original SWFs."""

import json

from utils import managers, save_data, text


CATALOG = [
    {
        "interior_id": 201,
        "interior_name": "기본 오두막",
        "interior_desc": "The standard Dream World house.",
        "interior_size_w": 13,
        "interior_size_h": 13,
        "interior_category_id": 1,
        "interior_category_name": "House",
        "place_type": 0,
        "kinomi_id": None,
        "kinomi": None,
        "price": 0,
        "kinomi_id2": None,
        "kinomi2": None,
        "price2": 0,
        "kinomi_id3": None,
        "kinomi3": None,
        "price3": 0,
    },
    {
        "interior_id": 202,
        "interior_name": "통나무집",
        "interior_desc": "집 외관을 바꿉니다. 실내는 기본 오두막을 사용합니다.",
        "interior_size_w": 13,
        "interior_size_h": 13,
        "interior_category_id": 1,
        "interior_category_name": "집",
        "place_type": 0,
        "kinomi_id": 149,
        "kinomi": None,
        "price": 5,
        "kinomi_id2": None,
        "kinomi2": None,
        "price2": 0,
        "kinomi_id3": None,
        "kinomi3": None,
        "price3": 0,
    },
    {
        "interior_id": 203,
        "interior_name": "드림 하우스",
        "interior_desc": "집 외관을 바꿉니다. 실내는 기본 오두막을 사용합니다.",
        "interior_size_w": 13,
        "interior_size_h": 13,
        "interior_category_id": 1,
        "interior_category_name": "집",
        "place_type": 0,
        "kinomi_id": 150,
        "kinomi": None,
        "price": 5,
        "kinomi_id2": None,
        "kinomi2": None,
        "price2": 0,
        "kinomi_id3": None,
        "kinomi3": None,
        "price3": 0,
    },
]

# 201/202/203 are complete island exteriors, not room furniture.
# Prices are local-server defaults; the original price table was not archived.

DEFAULT_FURNITURE = [
    {"my_interior_id": -1, "interior_id": 9990001, "interior_name": "보물상자", "interior_category_id": 26, "interior_size_w": 6, "interior_size_h": 5, "place_type": 2},
    {"my_interior_id": -2, "interior_id": 9990003, "interior_name": "친구보드", "interior_category_id": 26, "interior_size_w": 10, "interior_size_h": 7, "place_type": 1},
]


def _state():
    state = save_data.read_entralink_data()
    state.setdefault("interiors", [{"my_interior_id": 1, "interior_id": 201}])
    state.setdefault("interior_layout", [])
    return state


def _save(state):
    from game_sync_server.entralinked.utility.db_manager import db
    db.write(save_data.gscd, "game_sync", state)


def _localized(entry):
    result = dict(entry)
    berry_id = result.get("kinomi_id")
    if berry_id is not None:
        result["kinomi"] = text.lookup_str("item", berry_id)
    owned = next((i for i in _state()["interiors"] if i["interior_id"] == result["interior_id"]), None)
    result["my_interior_id"] = owned["my_interior_id"] if owned else None
    result.update({"is_ds": 0, "new_flag": 0, "limited_flag": 0})
    return result


def GET_interior_catalog_list(_query):
    return json.dumps([{
        "interior_catalog_id": 1,
        "interior_catalog_name": "Dream Catalogue",
        "interior_catalog_desc": "Restored local catalogue",
    }]).encode()


def GET_interior_list(_query):
    return json.dumps([_localized(entry) for entry in CATALOG]).encode()


def POST_my_interior_insert(query):
    interior_id = int(query["interior_id"])
    entry = next((item for item in CATALOG if item["interior_id"] == interior_id), None)
    if entry is None:
        raise ValueError(f"Unknown interior: {interior_id}")

    state = _state()
    owned = next((item for item in state["interiors"] if item["interior_id"] == interior_id), None)
    if owned is None:
        berry_item_id = entry.get("kinomi_id")
        price = int(entry.get("price") or 0)
        if price:
            managers.chest.remove_item(berry_item_id, price)
        next_id = max((item["my_interior_id"] for item in state["interiors"]), default=0) + 1
        owned = {"my_interior_id": next_id, "interior_id": interior_id}
        state["interiors"].append(owned)
        _save(state)
    return json.dumps([owned]).encode()


def GET_interior_change_update(query):
    my_interior_id = int(query["my_interior_id"])
    state = _state()
    owned = next(item for item in state["interiors"] if item["my_interior_id"] == my_interior_id)
    member = save_data.read_player_data()["member"]
    catalog = next(item for item in CATALOG if item["interior_id"] == owned["interior_id"])
    if catalog["interior_category_id"] == 1:
        member["island_id"] = owned["interior_id"]
        save_data.write_player_data({"island_id": owned["interior_id"]})
    return b"{}"


def POST_interior_layout_update(query):
    state = _state()
    values = query.get("interior", [])
    if not isinstance(values, list):
        values = [values]
    # Connection.as serializes ActionScript arrays as interior[0], interior[1].
    values += [value for key, value in sorted(query.items()) if key.startswith("interior[")]
    owned_by_id = {int(item["my_interior_id"]): item for item in state["interiors"]}
    owned_by_id.update({item["my_interior_id"]: item for item in DEFAULT_FURNITURE})
    layout = []
    for value in values:
        parts = str(value).split("_")
        if len(parts) != 4:
            continue
        my_interior_id, x, y, arranged = map(int, parts)
        if not arranged or my_interior_id not in owned_by_id:
            continue
        owned = owned_by_id[my_interior_id]
        catalog = next(item for item in CATALOG + DEFAULT_FURNITURE if item["interior_id"] == owned["interior_id"])
        if catalog["interior_category_id"] in (1, 2, 3):
            continue
        layout.append({
            "my_interior_id": my_interior_id,
            "interior_id": owned["interior_id"],
            "interior_name": catalog["interior_name"],
            "interior_category_id": catalog["interior_category_id"],
            "interior_size_w": catalog["interior_size_w"],
            "interior_size_h": catalog["interior_size_h"],
            "place_type": catalog["place_type"],
            "x": x,
            "y": y,
            "arrangement_flag": 1,
            "movable_flag": 1,
            "special_flag": 0,
            "roatation": 0,
        })
    state["interior_layout"] = layout
    _save(state)
    return b"{}"


def arranged_interiors():
    """Filter legacy misclassified houses from room furniture without deleting saves."""
    valid_ids = {item["interior_id"] for item in DEFAULT_FURNITURE}
    return [item for item in _state()["interior_layout"] if item.get("interior_id") in valid_ids]
