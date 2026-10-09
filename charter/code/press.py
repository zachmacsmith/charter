"""The Press Act (review 12 §2.x row C1; review 14 §4.4; D-33): who may open a channel, as default law (channels.v2 worlds only).

Store-based. Row:
  right    the right opening a channel needs (open_channel). Seam: channels.found_right, read when an agent opens a channel.
           Today: "press" (the Media's right: create_channel needed it). Residual (no Act, or repealed): anyone may open a channel
           (D-33). Without the default code the seam reads spec channels.found_right (null: anyone).
Selected only where channels.v2 is on (Act.when), so every other world's code (and its Act ids) is unchanged.
"""
from __future__ import annotations

from charter import lawlang as L
from charter.code import Act, register

NAME = "Press Act"

SOURCE = '''
title = "Press Act"
intent = "Default code: opening a channel (a group, a newspaper, a chamber, a secret cell) needs the right RIGHT, held at the start by the Media. Laws grant and revoke the right as before. Without this Act anyone may open a channel."
RIGHT = "press"
'''


def today(sp: dict) -> dict:
    return {"RIGHT": "press"}


def check(key, value, sp):
    if key == "right":
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip() or len(value) > 60:
            raise L.LawError(f"RIGHT is the name of a right (e.g. \"press\") or None, not {value!r}")
        return value.strip()
    raise L.LawError(f"no rule {key!r} in the {NAME}")


def describe(rows: dict) -> str:
    r = rows["right"]
    return "anyone may open a channel" if r is None else f"opening a channel needs the {r} right"


def when(sp: dict) -> bool:
    return bool((sp.get("channels") or {}).get("v2"))


ACT = register(Act(
    name=NAME, rank="statute", source=SOURCE.strip() + "\n", keys={"RIGHT": "right"}, residual={"right": None}, today=today,
    check=check, describe=describe, covers=("C1",), seams=("channels:found_right",), when=when,
    doc="Who may open a channel (channels.v2); the residual is anyone (D-33)."))
