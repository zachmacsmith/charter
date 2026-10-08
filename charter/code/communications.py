"""The Communications Act (review 12 §2.6, rows M1 and M2; top-10 #4): private-message rationing as default law.

Store-based. Rows:
  limit    the general private-message limit per agent per round (new messages and replies together). Seam: Kernel.dm_limit, when
           no one has set a general limit (set_dm_limit for everyone); each agent's drawn extra (dm_extra, P) is added on top and the
           hard cap (dm_step.max_per_round, X, Kernel.dm_cap) bounds the result. Today: spec dm_step.dms_per_round.
           Residual (no Act): no rationing, i.e. the hard cap.
  office   the class whose members hold dm_rules (the right to change the limit) when the world begins. Seam: generator.generate,
           read once at generation (start_rule); later, laws grant and revoke dm_rules as before. Today: spec dm_step.controller.
           Residual: nobody holds dm_rules.
The hard cap stays X (model cost) and is not part of the Act.
"""
from __future__ import annotations

from charter import lawlang as L
from charter.code import Act, register

NAME = "Communications Act"
CLASSES = ("worker", "scientist", "legislator", "media", "board", "fixer")

SOURCE = '''
title = "Communications Act"
intent = "Default code: private messages are rationed. Each agent may send LIMIT private messages per round (new messages and replies together), plus its own small drawn extra, never above the world's hard cap. Holders of dm_rules may change the limit for everyone or for one agent (set_dm_limit), and laws may too. The members of the class OFFICE hold dm_rules when the world begins (read once, at the start). Without this Act messages are not rationed (only the hard cap applies) and nobody starts with dm_rules."
LIMIT = 5
OFFICE = "media"
'''


def today(sp: dict) -> dict:
    dmc = sp.get("dm_step") or {}
    return {"LIMIT": int(dmc.get("dms_per_round", 5)), "OFFICE": dmc.get("controller", "media")}


def check(key, value, sp):
    if key == "limit":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value) or value < 0:
            raise L.LawError("LIMIT is a whole number of private messages, at least 0")
        return int(value)
    if key == "office":
        if value is None:
            return None
        if not isinstance(value, str) or value.strip().lower() not in CLASSES:
            raise L.LawError(f"OFFICE is a class ({', '.join(CLASSES)}) or None, not {value!r}")
        return value.strip().lower()
    raise L.LawError(f"no rule {key!r} in the {NAME}")


def describe(rows: dict) -> str:
    lim, office = rows["limit"], rows["office"]
    return (("private messages are not rationed (only the hard cap)" if lim is None else
             f"{lim} private messages per agent per round (plus each agent's drawn extra, under the hard cap)")
            + f"; dm_rules held at the start by {office + ' members' if office else 'nobody'}")


ACT = register(Act(
    name=NAME, rank="statute", source=SOURCE.strip() + "\n", keys={"LIMIT": "limit", "OFFICE": "office"},
    residual={"limit": None, "office": None}, today=today, check=check, describe=describe, covers=("M1", "M2"),
    seams=("kernel:Kernel.dm_limit", "generator:generate"), start=("office",),
    doc="Default DM limit and who holds dm_rules at the start; the hard cap stays X."))
