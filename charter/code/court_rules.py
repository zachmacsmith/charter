"""The Court Rules Act (review 12 §2.8, rows J1 and J2): the courts' default rules as default law.

Store-based. Rows (courts.DEFAULTS before; laws' own court rules, set_court_rule under law.v2, still take precedence):
  deadline           rounds a case may wait for a ruling before it is dismissed. Seams: courts.rules (law.v2),
                     courts.change_open_case (law.v1: the filing's deadline). Today 3. Residual: courts.BOUNDS' longest wait (20).
  panel              judges whose votes decide a case (a majority of the panel). Seam: courts.rules (law.v2; law.v1 has one
                     judge). Today 1. Residual: 1 (any one judge).
  rulings_per_round  rulings (and panel votes) a judge may give per round. Seams: courts.rules (law.v2), actions._rule (law.v1).
                     Today 3. Residual: courts.BOUNDS' most (20: no cap of its own).
"""
from __future__ import annotations

from charter import lawlang as L
from charter.code import Act, register

NAME = "Court Rules Act"
BOUNDS = {"deadline": (1, 20), "panel": (1, 9), "rulings_per_round": (1, 20)}      # courts.BOUNDS (checked equal in the tests)

SOURCE = '''
title = "Court Rules Act"
intent = "Default code: how the courts work where no law sets its own court rules. A case not ruled on within DEADLINE rounds of its filing is dismissed. PANEL judges hear each case and a majority of them decides it. A judge gives at most RULINGS_PER_ROUND rulings (or panel votes) per round. A law's own court rules (set_court_rule) take precedence. Without this Act a case may wait 20 rounds, one judge decides, and judges are not limited below 20 rulings a round."
DEADLINE = 3
PANEL = 1
RULINGS_PER_ROUND = 3
'''


def today(sp: dict) -> dict:
    from charter import courts as CO
    return {"DEADLINE": CO.DEFAULTS["deadline"], "PANEL": CO.DEFAULTS["panel"],
            "RULINGS_PER_ROUND": CO.DEFAULTS["rulings_per_round"]}


def check(key, value, sp):
    if key not in BOUNDS:
        raise L.LawError(f"no rule {key!r} in the {NAME}")
    lo, hi = BOUNDS[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value) or not lo <= int(value) <= hi:
        raise L.LawError(f"{key.upper()} is a whole number from {lo} to {hi}")
    return int(value)


def describe(rows: dict) -> str:
    return (f"a case waits at most {rows['deadline']} rounds for a ruling; panels of {rows['panel']}; "
            f"at most {rows['rulings_per_round']} rulings per judge per round")


ACT = register(Act(
    name=NAME, rank="statute", source=SOURCE.strip() + "\n",
    keys={"DEADLINE": "deadline", "PANEL": "panel", "RULINGS_PER_ROUND": "rulings_per_round"},
    residual={"deadline": 20, "panel": 1, "rulings_per_round": 20}, today=today, check=check, describe=describe,
    covers=("J1", "J2"), seams=("courts:rules", "courts:change_open_case", "actions:_rule"),
    doc="Case deadline, panel size and rulings per judge per round; laws' own court rules take precedence."))
