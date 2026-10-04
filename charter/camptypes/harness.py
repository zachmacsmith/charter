"""A small harness to exercise camp types without models: build a world whose camps are exactly the types you name, then play rounds
with chosen inputs. Used by the tests, the calibration script, and other camp-type authors (Camps-B).

    k = world(["tutorial", "cartel"], workers=4)          # a Kernel; camps camp1, camp2 in that order; every Worker holds every right
    out = play(k, {"camp2": {"Ada": [3], "Bram": [3]}})   # one round: inputs submitted, end of round run; returns {camp: {agent: yield}}
"""
from __future__ import annotations

from charter import generator
from charter import spec as S
from charter.kernel import Kernel

BASE_SETS = ["rounds=30", "hidden.enabled=false", "projects.enabled=false", "events.enabled=false", "shared_archive.enabled=false",
             "observer.enabled=false", "law_level=L2", "library=none", "constitution=assembly"]


def spec(types, workers=4, others=0, sets=(), all_rights=True, typed=None) -> dict:
    sp = S.apply_overrides(S.load("base"), BASE_SETS + [
        f"agents={{worker: {workers}, scientist: 0, legislator: {others}, media: 0, board: 0, fixer: 0}}", "camps.model=types"])
    t = dict(typed or {})
    t["set"] = [x if isinstance(x, dict) else {"type": x} for x in types]
    sp["camps"]["typed"] = t
    sp["camps"]["typed"].setdefault("holders_per_worker", [len(types), len(types)] if all_rights else [1, 2])
    return S.apply_overrides(sp, list(sets))


def world(types, workers=4, others=0, seed=1, sets=(), all_rights=True, typed=None) -> Kernel:
    inst = generator.generate(spec(types, workers, others, sets, all_rights, typed), seed)
    return Kernel(inst)


def submit(k, cid, aid, x) -> str:
    from charter import actions as A
    return A.act(k, aid, "harvest", {"camp": cid, "x": list(x)})


def play(k, inputs: dict, end=True) -> dict:
    """One round: start_round, every input harvested/submitted (in agent order), end_round. Returns {camp: {agent: total yield}}
    from this round's harvest events (paid at once or at the end of the round)."""
    k.start_round()
    r = k.r
    n0 = len(k.events)
    for cid in sorted(inputs):
        for aid in sorted(inputs[cid]):
            submit(k, cid, aid, inputs[cid][aid])
    if end:
        k.end_round()
    out: dict = {}
    for e in k.events[n0:]:
        if e["type"] == "harvest" and e["round"] == r:
            out.setdefault(e["data"]["camp"], {}).setdefault(e["agent"], 0.0)
            out[e["data"]["camp"]][e["agent"]] += e["data"]["yield"]
    return out


def workers(k) -> list:
    return sorted(a for a in k.players() if k.w["agents"][a]["cls"] == "worker")
