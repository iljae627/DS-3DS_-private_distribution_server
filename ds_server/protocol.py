from __future__ import annotations

import base64
from urllib.parse import parse_qs


def modified_b64_decode(value: str) -> str:
    translated = value.replace("*", "=").replace("?", "/").replace(">", "+").replace("-", "/")
    try:
        decoded = base64.b64decode(translated + "===", validate=False).decode("utf-8")
        if any(ord(char) < 0x20 and char not in "\r\n\t" for char in decoded):
            return value
        return decoded
    except (ValueError, UnicodeError):
        return value


def decode_dls_form(body: bytes) -> dict[str, str]:
    parsed = parse_qs(body.decode("ascii", errors="replace"), keep_blank_values=True)
    return {key: modified_b64_decode(values[0]) for key, values in parsed.items()}


def language_attr(language_id: int) -> str:
    return {1: "J", 2: "E", 3: "F", 4: "I", 5: "G", 7: "S", 8: "K"}.get(language_id, "E")
