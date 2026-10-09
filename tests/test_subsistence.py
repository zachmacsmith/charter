"""Subsistence (charter/subsistence.py, review 15 S1-S3): the ration, hunger stages and the hazard, spoilage, the hunger gate, the
food camps (forest, fields, the hunt), stores and institution-owned stores, and byte-identity with the flag off. No model calls."""
from __future__ import annotations

import json

import pytest

from charter import action_registry as AR
from charter import actions as A
from charter import accounts as AC
from charter import features as FT
from charter import generator
from charter import mortality as MO
from charter import primitives as PR
from charter import spec as S
from charter import subsistence as SB
from charter.kernel import Kernel

SMALL = "agents={worker: 8, scientist: 0, legislator: 0, media: 0, board: 0, fixer: 1}"


def world(preset="nature_subsistence", extra=(), seed=3, rounds=12, constitution=False):
    sp = S.apply_overrides(S.load(preset), [f"rounds={rounds}", "shared_archive.enabled=false", *extra])
    inst = generator.generate(sp, seed)
    k = Kernel(inst)
    if constitution:
        k.enact(k.new_law(inst["constitution_code"], "constitution"))
    return inst, k


def small(extra=(), **kw):
    return world(extra=(SMALL, *extra), **kw)


def end_round(k):
    """One round's start and end (no turns), as the runner frames it."""
    k.begin_round_cause(k.r, "round_start")
    k.start_round()
    k.phase("end_of_round")
    k.end_round()
    k.end_round_cause()


def eaters(k):
    return SB.eaters(k)


def set_food(k, aid, q):
    h = k.w["agents"][aid]["holdings"]
    h.pop("food", None)
    if q:
        h["food"] = float(q)


# ---------------------------------------------------------------------- the flag
def test_off_by_default_and_nothing_installed():
    inst, k = world("nature_design")
    assert not SB.enabled(inst) and "subsistence" not in k.w
    assert all("food" not in a["endowment"] for a in inst["agents"]) and "food" not in inst["spec"]["unit_values"]
    assert SB.state_lines(k, inst["agents"][0]["id"]) == [] and SB.snapshot_fields(k) == {} and SB.truth(k) == {}
    assert SB.law_api(k, "L1") == {}
    with pytest.raises(A.ActionError, match="unknown action"):
        A.act(k, inst["agents"][0]["id"], "farm", {"camp": "camp1", "sow": 1})


def test_on_installs_state_food_and_value():
    inst, k = small()
    assert FT.on("subsistence", k) and "subsistence" in k.w and k.w["unit"]["food"] == 1.0
    for a in inst["agents"]:
        if a["cls"] == "fixer":
            assert "food" not in a["endowment"]                                      # exempt (U6)
        else:
            assert 4 <= a["endowment"]["food"] <= 8


def test_schema_refuses_upkeep_with_the_ration_and_legacy_camps():
    from charter import schema as SC
    sp = S.load("nature_subsistence")
    assert SC.validate(sp) == []
    bad = S.apply_overrides(S.load("nature_subsistence"), ["resources.upkeep.enabled=true"])
    assert any("replaces resources.upkeep" in e for e in SC.validate(bad))
    bad = S.apply_overrides(S.load("nature_subsistence"), ["camps.model=legacy"])
    assert any("camps.model: types" in e for e in SC.validate(bad))


# ---------------------------------------------------------------------- the ration and the stages
def test_ration_tolerance_and_a_missed_meal_keeps_the_fraction():
    inst, k = small(["subsistence.spoil=0"])
    a, b, c = eaters(k)[:3]
    set_food(k, a, 1.0)
    set_food(k, b, 0.999999999)
    set_food(k, c, 0.6)
    end_round(k)
    assert k.bal(a, "food") == 0 and k.bal(b, "food") == pytest.approx(0, abs=1e-6)
    assert SB.stage(k, a) == 0 and SB.stage(k, b) == 0
    assert k.bal(c, "food") == pytest.approx(0.6) and SB.stage(k, c) == -1


def test_stages_fall_one_per_missed_meal_and_recover_one_per_meal():
    inst, k = small(["subsistence.spoil=0", "subsistence.hazard={step: 0.15, max_rounds: 99}", "subsistence.frailty=[0, 0]"])
    a = eaters(k)[0]
    seen = []
    set_food(k, a, 0)
    for _ in range(3):
        end_round(k)
        seen.append(SB.stage(k, a))
    assert seen == [-1, -2, -2]
    set_food(k, a, 1)
    end_round(k)
    assert SB.stage(k, a) == -1 and SB.state(k)["missed"][a] == 0           # a starving agent that eats is hungry
    set_food(k, a, 1)
    end_round(k)
    assert SB.stage(k, a) == 0                                              # and fed after a second meal
    hunger = [e for e in k.events if e["type"] == "hunger" and e["agent"] == a]
    assert [e["data"]["stage"] for e in hunger] == [-1, -2, -1, 0] and hunger[0]["vis"] == "public"   # U2 (b): public, coarse


def test_hazard_never_before_the_third_missed_meal_and_max_rounds_forces_death():
    inst, k = small(["subsistence.frailty=[1, 1]"])                         # certain death once the hazard applies
    for a in eaters(k):
        set_food(k, a, 0)
    end_round(k)
    end_round(k)
    assert all(MO.alive(k, a) for a in eaters(k)) and len(eaters(k)) == 8   # two missed meals: nobody dies
    end_round(k)
    assert eaters(k) == []                                                  # the third: frailty 1 kills
    dead = [e for e in k.events if e["type"] == "disabled"]
    assert len(dead) == 8 and all(e["data"]["cause"] == "starvation" and "starved" in e["data"]["text"] for e in dead)
    inst, k = small(["subsistence.frailty=[0, 0]", "subsistence.hazard={step: 0, max_rounds: 2}"])
    a = eaters(k)[0]
    set_food(k, a, 0)
    for _ in range(3):
        end_round(k)
    assert MO.alive(k, a)                                                   # n = 1 < max_rounds, hazard 0
    end_round(k)
    assert not MO.alive(k, a)                                               # n = 2: forced
    assert SB.state(k)["log"][-1]["deaths"] == [a]


def test_hazard_is_deterministic_and_independent_of_order():
    def deaths(order_reverse):
        inst, k = small()
        for a in eaters(k):
            set_food(k, a, 0)
        if order_reverse:
            k.w["agents"] = dict(reversed(list(k.w["agents"].items())))
        out = []
        for _ in range(6):
            end_round(k)
            out.append(sorted(SB.state(k)["log"][-1]["deaths"]))
        return out
    assert deaths(False) == deaths(True)


def test_frailty_is_hidden_from_agents():
    inst, k = small()
    a = eaters(k)[0]
    set_food(k, a, 0)
    for _ in range(3):
        end_round(k)
    f = SB.frailty(k, a)
    from charter import context as CX
    texts = "\n".join(SB.state_lines(k, a))
    texts += CX.core_prompt(inst, next(x for x in inst["agents"] if x["id"] == a), k)
    texts += json.dumps([e for e in k.events if k.can_see(a, e)])
    assert str(f) not in texts and f"{f:.2f}" not in texts and "frailty" not in texts


def test_exempt_classes_never_eat():
    inst, k = small()
    fixer = next(a for a, v in k.w["agents"].items() if v["cls"] == "fixer")
    assert SB.exempt(k, fixer) and fixer not in eaters(k)
    for _ in range(4):
        end_round(k)
    assert SB.stage(k, fixer) == 0 and MO.alive(k, fixer) and SB.state_lines(k, fixer)[:1] != ["Hunger: fed."]


# ---------------------------------------------------------------------- spoilage and conservation
def test_spoilage_in_every_account():
    inst, k = small(["subsistence.ration=0"])
    a = eaters(k)[0]
    set_food(k, a, 10)
    k._add("reserve", "food", 20)
    end_round(k)
    assert k.bal(a, "food") == pytest.approx(8.5) and k.bal("reserve", "food") == pytest.approx(17.0)
    others = sum(float(x["endowment"].get("food", 0)) for x in inst["agents"] if x["id"] != a)
    assert SB.state(k)["log"][-1]["spoiled"] == pytest.approx(1.5 + 3.0 + 0.15 * others)


def test_ration_and_spoilage_are_the_only_food_sinks():
    inst, k = small()
    t0 = AC.totals(k).get("food", 0.0)
    end_round(k)
    rec = SB.state(k)["log"][-1]
    assert AC.totals(k).get("food", 0.0) == pytest.approx(t0 - rec["ate"] * 1.0 - rec["spoiled"])


def test_lasts_projection():
    c = SB.cfg({})
    assert SB.lasts(c, 0.9) == 0 and SB.lasts(c, 1) == 1 and SB.lasts(c, 5) == 3
    inst, k = small()
    a = eaters(k)[0]
    set_food(k, a, 5)
    line = SB.state_lines(k, a)[0]
    assert line.startswith("Food: 5 ") and "lasts about 3 rounds" in line
    set_food(k, a, 0.6)
    assert any(x.startswith("Warning: you hold 0.6 food") for x in SB.state_lines(k, a))


# ---------------------------------------------------------------------- the hunger gate
def test_fed_values_follow_the_design():
    assert AR.REG["attack"].fed == 0 and AR.REG["propose"].fed == 0 and AR.REG["forge"].fed == 0
    assert AR.REG["transfer"].fed == -2 and AR.REG["harvest"].fed == -2 and AR.REG["manual"].fed == -2
    assert AR.REG["vote"].fed == -2                                        # U14 (the lead): starving agents keep their vote
    assert AR.REG["lend"].fed == -1 and AR.REG["rule"].fed == -1 and AR.REG["act_for"].fed == -1


def test_hungry_agents_are_refused_with_the_reason_and_lose_actions():
    inst, k = small()
    a, b = eaters(k)[:2]
    SB.state(k)["stage"][a] = -1
    with pytest.raises(A.ActionError, match="you are hungry: create_contract needs you fed"):
        A.act(k, a, "create_contract", {"name": "x", "code": "title = 'x'\n"})
    assert A.act(k, a, "transfer", {"to": b, "item": "food", "qty": 1}).startswith("Sent 1 food")
    names = [x.name for x in AR.available(inst, k, k.agent(a))]
    assert "create_contract" not in names and "transfer" in names
    assert SB.actions_after_hunger(k, a, 5) == 4 and SB.actions_after_hunger(k, a, 2) == 2
    SB.state(k)["stage"][a] = -2
    assert SB.actions_after_hunger(k, a, 5) == 2 and SB.actions_after_hunger(k, a, 3) == 1 and SB.actions_after_hunger(k, a, 1) == 1
    with pytest.raises(A.ActionError, match="you are starving"):
        A.act(k, a, "write_file", {"name": "n", "text": "t"})
    assert SB.yield_mult(k, a) == 0.5 and SB.yield_mult(k, b) == 1.0


def test_agency_checks_the_principal_too():
    inst, k = world("society", ["subsistence.enabled=true", "law.v2=true", "contracts.enabled=true"], constitution=True)
    a, b, c = eaters(k)[:3]
    out = A.act(k, a, "authorize", {"agent": b, "action": "transfer", "item": "food", "qty": 2})
    gid = out.split()[1].rstrip(":")
    SB.state(k)["stage"][a] = -2                                            # the principal starves: transfer is still allowed
    assert "For " in A.act(k, b, "act_for", {"auth": gid, "to": c, "qty": 1})
    SB.state(k)["stage"][b] = -2                                            # a starving actor cannot act for others
    with pytest.raises(A.ActionError, match="act_for needs you at most hungry"):
        A.act(k, b, "act_for", {"auth": gid, "to": c, "qty": 1})


# ---------------------------------------------------------------------- laws
RELIEF = '''title = "Relief"
intent = "Everyone with less than a meal gets one from the reserve at the end of each round."
def on_round_end(r):
    for a in agents():
        if food_of(a) < 1:
            move("reserve", a, "food", 1)
'''


def test_a_relief_law_lands_before_the_ration_and_reads_hunger():
    inst, k = world("society", ["subsistence.enabled=true", "law.v2=true"], constitution=True)
    lid = k.new_law(RELIEF, "relief")
    k.enact(lid)
    k._add("reserve", "food", 500)
    a = eaters(k)[0]
    set_food(k, a, 0)
    end_round(k)
    assert SB.stage(k, a) == 0 and k.bal(a, "food") == pytest.approx(0)    # relieved, then ate
    api = k.api_for(lid)
    assert api["hunger"](a) == "fed" and api["food_of"](a) == 0 and api["stores"]() == {}


def test_the_ration_hunger_and_spoilage_are_physics():
    for n in ("eat", "hunger", "spoil"):
        p = PR.get(n)
        assert p.tier == "P" and not p.blockable and not p.before and p.routed and p.causes == ("world",)
    assert "starvation" in MO.CAUSES and MO.CAUSE_TEXT["starvation"]
