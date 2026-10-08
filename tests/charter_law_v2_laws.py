"""Library-style laws written with law.v2's new-style hooks (P3.1), shared by tests/test_charter_law_v2.py and the golden case
society_law_v2 (tests/test_charter_golden.py). They are test fixtures, not library entries: `register()` adds them to library.LIB
for the duration of a test, so start_laws can name them."""
from __future__ import annotations

from contextlib import contextmanager

V2_LAWS = {
    # review 09 §13.2: a welfare law reacting to a law-caused change (a fine)
    "Fine Relief": '''
title = "Fine Relief"
intent = "When a fine leaves someone with less than 5 of the fined good, the treasury returns half the fine."

def after_move(p, chain):
    if p["why"] != "fine" or p["result"]["moved"] <= 0:
        return
    victim = p["src"]
    if balance(victim, p["item"]) < 5:
        move(treasury(), victim, p["item"], p["result"]["moved"] / 2)
        notify(victim, "Fine Relief returned half of your fine.")
        state["relief"] = state.get("relief", 0) + 1
        state["chain"] = [f["kind"] for f in chain]
''',
    # review 09 §13.3: an inheritance law on end_life, whatever the cause
    "Equal Partition": '''
title = "Equal Partition"
intent = "An estate is split equally among the deceased's living children; the rest follows the bequest."

def after_end_life(p, chain):
    if p["cause"] == "departure":
        return
    kids = [c for c in children_of(p["agent"]) if c in agents()]
    state["deaths"] = state.get("deaths", 0) + 1
    if not kids:
        return
    estate = "estate:" + p["agent"]
    for item, qty in p["result"]["estate"].items():
        for c in kids:
            move(estate, c, item, qty / len(kids))
    state["partitions"] = state.get("partitions", 0) + 1
''',
    # a tax as a before-hook charge (paid to the law's treasury)
    "Harvest Tithe": '''
title = "Harvest Tithe"
intent = "A twentieth of every harvest goes to the treasury, whoever harvests."

def before_harvest(p, chain):
    return round_to(p["qty"] * 0.05, 3)
''',
    # a toll on agents' transfers as a dict verdict (charged to the sender, paid to the treasury)
    "Transfer Toll": '''
title = "Transfer Toll"
intent = "Two percent of every transfer is charged to the sender."

def before_move(p, chain):
    if p["why"] == "transfer":
        return {"charge": round_to(p["qty"] * 0.02, 3), "reason": "toll"}
    return None
''',
    # a ledger of every move, by its root cause (agents, laws, the world, the kernel)
    "Move Ledger": '''
title = "Move Ledger"
intent = "Counts every change of ownership by what caused it."

def after_move(p, chain):
    k = root_kind(chain)
    state[k] = state.get(k, 0) + 1
    if caused_by_law(chain, law_id()):
        state["own"] = state.get("own", 0) + 1
''',
    # an observer of every post, by its root cause
    "Speech Ledger": '''
title = "Speech Ledger"
intent = "Counts public speech by what caused it."

def after_post(p, chain):
    k = root_kind(chain)
    state[k] = state.get(k, 0) + 1
''',
    # a register of every death (world, agent or law caused)
    "Death Register": '''
title = "Death Register"
intent = "Every death is recorded in the gazette with its cause."

def after_end_life(p, chain):
    gazette("Death register: " + str(p["agent"]) + " (" + str(p["cause"]) + ")")
''',
    # constitutional review of drafts (a procedural law: it hooks a legal act)
    "Rights Review": '''
title = "Rights Review"
intent = "No draft may take away the vote, the right to propose, or speech."
PROTECTED = ["vote", "propose", "post"]

def before_propose(p, chain):
    d = p["draft"]
    for r in d["rights"]["revoke"] + d["rights"]["suspend"]:
        if r in PROTECTED:
            return {"block": True, "reason": "revokes a protected right: " + r}
    return None
''',
}

GOLDEN_LAWS = ["Harvest Tithe", "Transfer Toll", "Fine Relief", "Equal Partition", "Move Ledger", "Speech Ledger", "Death Register",
               "Rights Review"]


def register():
    from charter import library as LB
    for name, code in V2_LAWS.items():
        LB.LIB[name] = {"name": name, "category": "law_v2_test", "code": code.strip() + "\n"}


def unregister():
    from charter import library as LB
    for name in V2_LAWS:
        LB.LIB.pop(name, None)


@contextmanager
def registered():
    register()
    try:
        yield
    finally:
        unregister()
