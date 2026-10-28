from datetime import datetime

from utils import save_data

def localize_last_up_time(timestamp: int) -> str:
    if timestamp is None:
        return ""
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime(lang_formats[player_language])

lang_formats = {
    'ja': '%y/%m/%d %H:%M',
    'en': '%m/%d/%y %H:%M',
    'fr': '%d/%m/%y %H:%M',
    'it': '%d/%m/%y %H:%M',
    'de': '%d.%m.%y %H:%M',
    'es': '%d-%m-%y %H:%M',
    'ko': '%y.%m.%d %H:%M'
}

lang_index = {
    1: "ja",
    2: "en",
    3: "fr",
    4: "it",
    5: "de",
    7: "es",
    8: "ko"
}

try:
    player_language = lang_index.get(save_data.read_player_data().get("member", {}).get("langcode"), "ko")
except (KeyError, TypeError):
    player_language = "ko"
