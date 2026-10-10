"""dm_step.capacity: natural (an agent's DM capacity is physics: dms_per_round + its drawn dm_extra, under the hard cap; law and
dm_rules can only cap it) vs legacy (the limit set by law, else the Communications Act's LIMIT + extra, else the hard cap)."""
from __future__ import annotations

from charter import agents as AG
from charter import code as DC
from charter import generator
from charter import spec as S
from charter.kernel import Kernel

SMALL = ["rounds=6", "agents={worker: 10, scientist: 0, legislator: 0, media: 0, board: 0, fixer: 1}"]


def _nature(capacity, seed=3):
    sp = S.apply_overrides(S.load("nature_subsistence"), [*SMALL, f"dm_step.capacity={capacity}"])
    inst = generator.generate(sp, seed)
    k = Kernel(inst)
    k.begin_round_cause(phase="setup")
    DC.seed(k, inst)                                                      # as the runner does (no Acts here: a state of nature)
    return inst, k


def _code_world(capacity, sets=()):
    sp = S.apply_overrides(S.load("E4"), ["shared_archive.enabled=false", "code.enabled=true", f"dm_step.capacity={capacity}", *sets])
    inst = generator.generate(sp, 1)
    k = Kernel(inst)
    k.begin_round_cause(phase="setup")
    DC.seed(k, inst)
    return inst, k


def _workers(inst):
    return [a for a in inst["agents"] if a["cls"] == "worker"]


def test_specs_set_natural_capacity():
    for name in ("nature_subsistence", "nature_pairs", "ashwood"):
        assert S.load(name)["dm_step"]["capacity"] == "natural", name
    assert (S.load("E4").get("dm_step") or {}).get("capacity", "legacy") == "legacy"


def test_no_law_gives_base_plus_extra_and_varies_by_agent():
    inst, k = _nature("natural")
    base, cap = int(k.spec["dm_step"]["dms_per_round"]), k.dm_cap()
    lims = {}
    for a in _workers(inst):
        assert k.dm_limit(a["id"]) == min(cap, base + a["dm_extra"]) == k.dm_capacity(a["id"])
        assert k.dm_limit_source(a["id"]) == "capacity"
        lims[a["id"]] = k.dm_limit(a["id"])
    assert len(set(lims.values())) > 1 and max(lims.values()) < cap      # varies, and nobody is handed the hard cap of 10


def test_legacy_unchanged_in_a_state_of_nature():
    inst, k = _nature("legacy")
    for a in _workers(inst):
        assert k.dm_limit(a["id"]) == k.dm_cap() == 10                  # no law, no Act: the hard cap (the old residual)
        assert k.dm_limit_source(a["id"]) is None


def test_a_law_cap_lowers_capacity_but_never_raises_it():
    inst, k = _nature("natural")
    ws = _workers(inst)
    hi = max(ws, key=lambda a: a["dm_extra"])
    lo = min(ws, key=lambda a: a["dm_extra"])
    cap_hi, cap_lo = k.dm_capacity(hi["id"]), k.dm_capacity(lo["id"])
    assert cap_hi > cap_lo
    k.w["dm_limit"]["all"] = cap_lo                                       # a cap for everyone
    assert k.dm_limit(hi["id"]) == cap_lo and k.dm_limit_source(hi["id"]) == "law"
    assert k.dm_limit(lo["id"]) == cap_lo and k.dm_limit_source(lo["id"]) == "capacity"
    k.w["dm_limit"]["all"] = 10                                           # a limit above capacity does not raise anyone
    assert k.dm_limit(hi["id"]) == cap_hi and k.dm_limit(lo["id"]) == cap_lo
    k.w["dm_limit"]["agents"][lo["id"]] = 9                               # nor does one set for one agent
    assert k.dm_limit(lo["id"]) == cap_lo
    k.w["dm_limit"]["agents"][hi["id"]] = 1                               # the tightest cap wins
    assert k.dm_limit(hi["id"]) == 1 and k.dm_limit_source(hi["id"]) == "law"
    k.w["dm_limit"]["all"] = 0
    assert k.dm_limit(lo["id"]) == 0


def test_set_dm_limit_primitive_caps_under_natural():
    inst, k = _code_world("natural")
    a = _workers(inst)[0]
    capa = k.dm_capacity(a["id"])
    assert k.dm_limit(a["id"]) == capa                                    # the Act's LIMIT (+ extra) equals the capacity
    k.set_dm_limit(10, agent=a["id"])
    assert k.dm_limit(a["id"]) == capa
    k.set_dm_limit(1, agent=a["id"])
    assert k.dm_limit(a["id"]) == 1


def test_communications_act_limit_only_caps_under_natural():
    for limit, sets in ((1, ['code.select={"Communications Act": {"LIMIT": 1}}']),
                        (9, ['code.select={"Communications Act": {"LIMIT": 9}}'])):
        inst, k = _code_world("natural", sets)
        for a in _workers(inst):
            assert k.dm_limit(a["id"]) == min(k.dm_capacity(a["id"]), limit + a["dm_extra"])
        inst, k = _code_world("legacy", sets)
        for a in _workers(inst):
            assert k.dm_limit(a["id"]) == min(k.dm_cap(), limit + a["dm_extra"])   # legacy: the Act can raise it


def test_legacy_law_limit_is_exact():
    inst, k = _code_world("legacy")
    a = _workers(inst)[0]
    k.set_dm_limit(9, agent=a["id"])
    assert k.dm_limit(a["id"]) == 9                                       # legacy: a law may raise an agent's limit


def test_prompt_states_the_source():
    inst, k = _nature("natural")
    a = _workers(inst)[0]
    assert AG.dm_source(k, a["id"]) == " (your capacity)"
    k.w["dm_limit"]["agents"][a["id"]] = 0
    assert AG.dm_source(k, a["id"]) == " (capped by law)"
    inst, k = _nature("legacy")
    assert AG.dm_source(k, _workers(inst)[0]["id"]) == ""
