"""Files and context.

# STUB (owned by Context agent): the minimal contract (docs/parallel_build_contracts.md). State:
k.w["files"][aid] = {name: {"text", "tokens", "pinned", "origin"}}, k.w["file_space"][aid] (tokens beyond the scratchpad),
k.w["pin_slots"][aid], k.w["scratchpad"][aid]. The real module replaces this file at merge.
"""
from __future__ import annotations

MANUAL_SECTIONS: list = []


def tokens(text) -> int:
    return len(str(text)) // 4


def space_left(k, aid) -> int:
    used = sum(int(f.get("tokens", 0)) for f in (k.w.get("files") or {}).get(aid, {}).values())
    return int((k.w.get("file_space") or {}).get(aid, 0)) - used


def add_file(k, aid, name, text, origin) -> None:
    k.w.setdefault("files", {}).setdefault(aid, {})[str(name)] = {"text": str(text), "tokens": tokens(text), "pinned": False,
                                                                  "origin": str(origin)}
