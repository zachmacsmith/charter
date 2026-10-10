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
    assert [e["data"]["stage"] for e in hunger] == [-1, -2, -1, 0] and {e["vis"] for e in hunger} == {"monitor"}   # (user, 10 Oct)


def test_hunger_is_on_the_roster_never_a_public_event():
    inst, k = small(["subsistence.spoil=0"])
    a, b = eaters(k)[:2]
    set_food(k, a, 0)
    end_round(k)
    assert SB.stage(k, a) == -1
    assert f"Hunger now: hungry: {a}." in SB.state_lines(k, b)                # the coarse roster on everyone's state lines
    assert not [e for e in k.events if e["type"] == "hunger" and k.can_see(b, e)]
    assert not [e for e in k.events if e["type"] == "hunger" and k.can_see(a, e)]
    inst, k = small(["subsistence.spoil=0", "subsistence.visibility=private"])
    a, b = eaters(k)[:2]
    set_food(k, a, 0)
    end_round(k)
    assert not any(x.startswith("Hunger now") for x in SB.state_lines(k, b))
    assert any(x.startswith("HUNGRY") for x in SB.state_lines(k, a))


def test_there_is_no_eat_action_the_ration_is_automatic():
    assert "eat" not in AR.REG and not any("eat" == n for n in AR.ACTIONS_ORDER)
    inst, k = small(["subsistence.spoil=0"])
    a = eaters(k)[0]
    set_food(k, a, 3)
    names = [x.name for x in AR.available(inst, k, k.agent(a))]
    assert "eat" not in names
    with pytest.raises(A.ActionError, match="unknown action"):
        A.act(k, a, "eat", {})
    end_round(k)
    assert k.bal(a, "food") == pytest.approx(2)                            # drained 1, with no action at all


def test_eat_from_store_is_on_by_default_and_draws_only_on_own_stores():
    assert SB.DEFAULTS["eat_from_store"] is True
    for on_, want in ((False, -1), (True, 0)):
        inst, k = small(["subsistence.spoil=0", "subsistence.store_spoil=0", f"subsistence.eat_from_store={str(on_).lower()}"])
        a, b = eaters(k)[:2]
        builder(k, a)
        A.act(k, a, "build", {"kind": "store"})
        k._add("store:S1", "food", 5)
        set_food(k, a, 0.4)
        set_food(k, b, 0)
        end_round(k)
        assert SB.stage(k, a) == want and SB.stage(k, b) == -1               # b owns no store: never fed from a's
        assert k.bal("store:S1", "food") == pytest.approx(5 if not on_ else 4.4)
    from charter import lawlang as L
    with pytest.raises(L.LawError, match="only its owner"):
        k.apply("move", src="store:S1", dst=b, item="food", qty=1, why="ration")   # the ration's move reaches the owner only


def test_a_makers_child_starts_with_two_rounds_food():
    from charter import events as EV
    inst, k = small()
    a = eaters(k)[0]
    k.w.setdefault("life", {}).setdefault("maker_of", {})["kid"] = a
    k.w["agents"]["kid"] = {"id": "kid", "cls": "worker", "holdings": {}, "rights": []}
    assert SB.on_birth(k, "kid", a) == {"food": 2.0} and k.bal("kid", "food") == pytest.approx(2.0)
    assert SB.on_birth(k, a, None) == {}                                     # no Maker: nothing
    assert ("subsistence", "on_birth") in FT.PHASES["birth"] and PR.get("provision").tier == "P"
    assert EV is not None


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


# ---------------------------------------------------------------------- S2: the composer and the food camps
def food_camps(k, typ):
    return [cid for cid, c in sorted(k.w["camps"].items()) if c.get("role") == "subsistence" and c["type"] == typ]


FIELDS = "subsistence.fields.enabled=true"                                 # fields are parked (off by default): tests that farm


def test_the_composer_appends_forests_and_draws_nothing_else():
    for seed in range(1, 21):
        sets = ["shared_archive.enabled=false", SMALL]
        off = generator.generate(S.apply_overrides(S.load("nature_design"), sets), seed)
        on = generator.generate(S.apply_overrides(S.load("nature_subsistence"), sets), seed)
        n = len(off["camps"])
        assert on["camps"][:n] == off["camps"] and all(c["type"] not in ("forest", "fields") for c in off["camps"])
        assert [c["type"] for c in on["camps"][n:]] == ["forest"]          # fields parked; no camp-style hunt (review 19)
        assert all(c["role"] == "subsistence" and c["resource"] == "food" and c["open"] for c in on["camps"][n:])
        assert on["spec"]["unit_values"]["food"] == 1.0 and "food" not in off["spec"]["unit_values"]
        assert [a["rights"] for a in on["agents"]] == [a["rights"] for a in off["agents"]]
    inst = generator.generate(S.apply_overrides(S.load("nature_subsistence"), [
        "shared_archive.enabled=false", "agents={worker: 100, scientist: 0, legislator: 0, media: 0, board: 0, fixer: 1}"]), 1)
    fo = [c for c in inst["camps"] if c.get("role") == "subsistence"]
    assert [c["type"] for c in fo] == ["forest"] * 9                             # ceil(100/12); total capacity per agent unchanged
    assert sum(c["K"] for c in fo) == pytest.approx(700) and sum(c["game"]["K"] for c in fo) == pytest.approx(1000)
    assert all(c["S"] == pytest.approx(0.95 * c["K"]) and c["game"]["G"] == pytest.approx(0.95 * c["game"]["K"]) for c in fo)   # near capacity
    inst = generator.generate(S.apply_overrides(S.load("nature_subsistence"), [
        "shared_archive.enabled=false", "agents={worker: 100, scientist: 0, legislator: 0, media: 0, board: 0, fixer: 1}", FIELDS]), 1)
    types = [c["type"] for c in inst["camps"] if c.get("role") == "subsistence"]
    assert types.count("forest") == 9 and types.count("fields") == 3 and "weak_link" not in types
    assert sum(len(c["plots"]) for c in inst["camps"] if c["type"] == "fields") == 40


def test_fields_are_parked_out_of_the_prompt_and_the_actions():
    from charter import context as CX
    inst, k = small()
    a = next(x for x in inst["agents"] if x["cls"] != "fixer")
    assert not food_camps(k, "fields") and "farm" not in [x.name for x in AR.available(inst, k, a)]
    with pytest.raises(A.ActionError, match="unknown action 'farm'"):
        A.act(k, a["id"], "farm", {"camp": "camp7", "sow": 1})
    core = CX.core_prompt(inst, a, k)
    assert "farm" not in core and "fields" not in SB.rules_text(inst) and "plot" not in SB.rules_text(inst)
    inst, k = small([FIELDS])
    a = next(x for x in inst["agents"] if x["cls"] != "fixer")
    assert "farm" in [x.name for x in AR.available(inst, k, a)] and "fields" in SB.rules_text(inst)


def test_food_camps_ignore_open_classes():
    inst, k = world("society", ["subsistence.enabled=true", FIELDS])
    assert k.spec["camps"]["typed"]["open_classes"] == ["worker"]
    leg = next(a for a in eaters(k) if k.w["agents"][a]["cls"] == "legislator")
    social = next(cid for cid, c in k.w["camps"].items() if c.get("role") == "social")
    with pytest.raises(A.ActionError, match="Workers only"):
        A.act(k, leg, "harvest", {"camp": social, "x": [1]})
    assert A.act(k, leg, "harvest", {"camp": food_camps(k, "forest")[0]}).startswith("Foraged")
    assert A.act(k, leg, "hunt", {"camp": food_camps(k, "forest")[0]}).startswith("You hunt")
    assert A.act(k, leg, "farm", {"camp": food_camps(k, "fields")[0], "sow": 1}).startswith("Sowed 1 food")
    board = next(a for a, v in k.w["agents"].items() if v["cls"] == "board")
    with pytest.raises(A.ActionError):
        A.act(k, board, "harvest", {"camp": food_camps(k, "forest")[0]})
    with pytest.raises(A.ActionError):
        A.act(k, board, "hunt", {"camp": food_camps(k, "forest")[0]})


def test_forage_yield_refuge_and_the_round_cap():
    inst, k = small()
    a, b = eaters(k)[:2]
    f = food_camps(k, "forest")[0]
    c = k.w["camps"][f]
    c["S"] = c["K"] * 0.5
    f0 = k.bal(a, "food")
    A.act(k, a, "harvest", {"camp": f})
    assert k.bal(a, "food") - f0 == pytest.approx(3.0 * 0.5, abs=1e-3)
    A.act(k, a, "harvest", {"camp": f})
    with pytest.raises(A.ActionError, match="used your 2 forest actions"):
        A.act(k, a, "harvest", {"camp": f})
    with pytest.raises(A.ActionError, match="used your 2 forest actions"):
        A.act(k, a, "hunt", {"camp": f})                                   # hunting is a forest action too
    c["S"], c["harvested_this_round"] = c["K"] * 0.11, 0.0                  # just above the refuge (0.10 K)
    c["fn"]["yield"] = 100.0                                                # (a yield that would take far more)
    f0 = k.bal(b, "food")
    A.act(k, b, "harvest", {"camp": f})
    assert k.bal(b, "food") - f0 == pytest.approx(0.01 * c["K"], abs=1e-3)   # capped at the refuge
    A.act(k, b, "harvest", {"camp": f})
    assert k.bal(b, "food") - f0 == pytest.approx(0.01 * c["K"], abs=1e-3)   # nothing below it
    SB.state(k)["stage"][b] = -1
    SB.state(k)["forage"] = {}
    c["S"], c["harvested_this_round"], c["fn"]["yield"] = c["K"], 0.0, 3.0
    f0 = k.bal(b, "food")
    A.act(k, b, "harvest", {"camp": f})
    assert k.bal(b, "food") - f0 == pytest.approx(3.0 * 0.75, abs=1e-3)    # hungry: x0.75


def test_a_law_quota_applies_to_foraging_and_hunting():
    inst, k = world("society", ["subsistence.enabled=true", SMALL])         # S6: a forest reads the forager's polity's camp rules
    # (as every camp does, D-37); in J0 they are the camp's own
    a, b = eaters(k)[:2]
    f = food_camps(k, "forest")[0]
    k.w["camps"][f]["quota"] = 1
    A.act(k, a, "harvest", {"camp": f})
    with pytest.raises(A.ActionError, match="quota"):
        A.act(k, b, "harvest", {"camp": f})
    with pytest.raises(A.ActionError, match="quota"):
        A.act(k, b, "hunt", {"camp": f})
    assert b not in (k.w["camps"][f].get("hunts") or {})                  # a refused hunt enters nothing


def test_felling_shrinks_the_forest_and_clears_a_plot():
    inst, k = small([FIELDS])
    f = food_camps(k, "forest")[0]
    c = k.w["camps"][f]
    fl = c["fn"]["pair"]
    K0, plots0 = c["fn"]["K0"], len(k.w["camps"][fl]["plots"])
    a = eaters(k)
    for i in range(5):
        t0 = k.bal(a[i], "timber")
        assert "Felled 3 timber" in A.act(k, a[i], "harvest", {"camp": f, "fell": True})
        assert k.bal(a[i], "timber") - t0 == pytest.approx(3.0)
    assert c["K"] == pytest.approx(K0 * 0.95, abs=1e-3) and len(k.w["camps"][fl]["plots"]) == plots0 + 1
    assert any(e["type"] == "plot_cleared" for e in k.events)
    inst, k = small()                                                      # fields off: felling clears nothing
    f = food_camps(k, "forest")[0]
    assert k.w["camps"][f]["fn"]["pair"] is None
    for x in eaters(k)[:5]:
        assert "Felled 3 timber" in A.act(k, x, "harvest", {"camp": f, "fell": True})
    assert not any(e["type"] == "plot_cleared" for e in k.events)


def test_sow_ripen_reap_by_another_and_the_sower_is_told():
    inst, k = small(["subsistence.spoil=0", "subsistence.fields={enabled: true, blight: 0, noise: 0}"])
    a, b = eaters(k)[:2]
    fl = food_camps(k, "fields")[0]
    set_food(k, a, 6)
    assert A.act(k, a, "farm", {"camp": fl, "sow": 3}).startswith("Sowed 3 food on " + fl + " plot 1")
    assert k.bal(a, "food") == pytest.approx(3) and k.w["camps"][fl]["plots"][0]["status"] == "growing"
    with pytest.raises(A.ActionError, match="growing"):
        A.act(k, b, "farm", {"camp": fl, "reap": 1})
    end_round(k)
    end_round(k)
    assert k.w["camps"][fl]["plots"][0]["status"] == "growing"
    end_round(k)
    assert k.w["camps"][fl]["plots"][0]["status"] == "ripe"                 # ripe at the start of round sown + 3
    assert any(x.startswith("Your crops: " + fl + " plot 1 RIPE") for x in SB.state_lines(k, a))
    f0 = k.bal(b, "food")
    assert "sown by " + a in A.act(k, b, "farm", {"camp": fl, "reap": 1})  # liberty: anyone reaps (U1 residual)
    assert k.bal(b, "food") - f0 == pytest.approx(3 * 3.5)
    ev = next(e for e in k.events if e["type"] == "reap")
    assert set(ev["vis"]) == {a, b} and ev["data"]["sower"] == a
    p = k.w["camps"][fl]["plots"][0]
    assert p["status"] == "fallow" and p["fertility"] == pytest.approx(0.9)
    end_round(k)
    end_round(k)
    assert p["fertility"] == pytest.approx(1.0)                             # +0.2 a fallow round, up to 1


def test_sowing_from_one_food_and_its_limits():
    inst, k = small([FIELDS])
    a = eaters(k)[0]
    fl = food_camps(k, "fields")[0]
    set_food(k, a, 1)
    assert A.act(k, a, "farm", {"camp": fl, "sow": 1}).startswith("Sowed 1 food")
    set_food(k, a, 10)
    with pytest.raises(A.ActionError, match="between 1 and 3"):
        A.act(k, a, "farm", {"camp": fl, "sow": 4})
    with pytest.raises(A.ActionError, match="between 1 and 3"):
        A.act(k, a, "farm", {"camp": fl, "sow": 0.5})
    with pytest.raises(A.ActionError, match="growing, not fallow"):
        A.act(k, a, "farm", {"camp": fl, "sow": 1, "plot": 1})
    for p in k.w["camps"][fl]["plots"][1:]:
        p["status"] = "growing"
    with pytest.raises(A.ActionError, match="no fallow plot"):
        A.act(k, a, "farm", {"camp": fl, "sow": 1})
    with pytest.raises(A.ActionError, match="farmed, not harvested"):
        A.act(k, a, "harvest", {"camp": fl})


def test_rot_and_blight_are_deterministic():
    inst, k = small(["subsistence.fields={enabled: true, blight: 0, noise: 0, grow: 1}"])
    a = eaters(k)[0]
    fl = food_camps(k, "fields")[0]
    set_food(k, a, 3)
    A.act(k, a, "farm", {"camp": fl, "sow": 2})
    end_round(k)
    p = k.w["camps"][fl]["plots"][0]
    assert p["status"] == "ripe" and p["left"] == 1.0
    end_round(k)
    assert p["left"] == pytest.approx(0.5)                                  # unreaped through its first ripe round
    inst, k = small(["subsistence.fields={enabled: true, blight: 1}"])
    a = eaters(k)[0]
    fl = food_camps(k, "fields")[0]
    A.act(k, a, "farm", {"camp": fl, "sow": 1})
    for _ in range(3):
        end_round(k)
    assert k.w["camps"][fl]["plots"][0]["status"] == "fallow" and any(e["type"] == "crop_failed" for e in k.events)


TILLERS = '''title = "Tillers' Right"
intent = "Only the sower of a crop may reap it."
def before_reap(p, chain):
    for pl in plots(p["camp"]):
        if pl["id"] == p["plot"] and pl["sower"] != None and pl["sower"] != p["agent"]:
            return False
'''


def test_a_tillers_right_law_refuses_a_non_sower():
    inst, k = world("society", ["subsistence.enabled=true", "law.v2=true", "subsistence.fields={enabled: true, grow: 1, blight: 0}"],
                    constitution=True)
    k.enact(k.new_law(TILLERS, "tillers"))
    a, b = eaters(k)[:2]
    fl = food_camps(k, "fields")[0]
    set_food(k, a, 5)
    A.act(k, a, "farm", {"camp": fl, "sow": 2})
    end_round(k)
    with pytest.raises(A.ActionError, match="blocked"):
        A.act(k, b, "farm", {"camp": fl, "reap": 1})
    assert A.act(k, a, "farm", {"camp": fl, "reap": 1}).startswith("Reaped")


def test_food_camps_in_the_prompt_only_when_on():
    from charter import context as CX
    inst, k = small()
    a = next(x for x in inst["agents"] if x["cls"] != "fixer")
    core = CX.core_prompt(inst, a, k)
    assert "camp6 food (open forest: forage plants" in core and "[manual: Food]" in core and "hunt (hunt game" in core
    assert "Food. Every agent" in json.dumps(CX.build_manual(inst, k, a["id"]))
    inst, k = world("nature_design", [SMALL])
    core = CX.core_prompt(inst, next(x for x in inst["agents"] if x["cls"] != "fixer"), k)
    assert "food" not in core.lower() and "farm (" not in core and "hunt (" not in core


# ---------------------------------------------------------------------- review 19: the forest ecosystem (plants, game, the hunt)
def forest(k):
    f = food_camps(k, "forest")[0]
    return f, k.w["camps"][f]


def test_expected_catch_rises_with_the_party_then_thins():
    from charter.camptypes import forest as FO
    gp = SB.cfg({})["game"]
    per = {E: FO.expected_catch(gp, E) / E for E in (1, 2, 3, 4, 6, 8, 12)}
    assert per[1] == pytest.approx(1.15, abs=0.02) and per[6] == pytest.approx(2.26, abs=0.02)
    assert per[1] < per[2] < per[3] < per[4] < per[6] and per[6] > per[8] > per[12]     # better together, diminishing returns
    assert FO.expected_catch(gp, 4, 0.3) < 0.4 * FO.expected_catch(gp, 4, 1.0)          # fewer animals, fewer kills
    pl1, _ = FO.kill_chances(gp, 1, 1.0)
    pl6, _ = FO.kill_chances(gp, 6, 1.0)
    assert pl1 < 0.02 < 0.5 < pl6                                                        # a lone hunter rarely takes big game


def test_a_party_hunts_together_and_the_catch_is_shared_by_effort():
    inst, k = small(["subsistence.spoil=0", "subsistence.ration=0", "subsistence.seasons.enabled=false"])
    a, b, c, d, e = eaters(k)[:5]
    f, cm = forest(k)
    for x in (a, b, c):
        A.act(k, x, "hunt", {"camp": f, "party": "red"})
    A.act(k, a, "hunt", {"camp": f})                                         # a second unit, same party (effort 2)
    A.act(k, d, "hunt", {"camp": f})                                         # alone
    with pytest.raises(A.ActionError, match="already hunting"):
        A.act(k, a, "hunt", {"camp": f, "party": "blue"})
    assert cm["hunts"][a] == {"party": "red", "effort": 2} and cm["hunts"][d] == {"party": None, "effort": 1}
    from charter.camptypes import framework as CT
    assert "you are hunting here this round (2 effort, party red)" in CT.view(k, f, fresh=False).state_line(k, a)
    f0 = {x: k.bal(x, "food") for x in (a, b, c, d, e)}
    G0 = cm["game"]["G"]
    end_round(k)
    got = {x: round(k.bal(x, "food") - f0[x], 3) for x in (a, b, c, d, e)}
    res = {ev["agent"]: ev["data"] for ev in k.events if ev["type"] == "hunt_result"}
    assert set(res) == {a, b, c, d} and got[e] == 0
    red = res[a]["catch"]
    assert res[b]["catch"] == red and res[a]["hunters"] == sorted([a, b, c])
    assert got[a] == pytest.approx(2 * got[b], abs=2e-3) and got[b] == pytest.approx(got[c])   # shared by effort
    assert got[a] + got[b] + got[c] == pytest.approx(red, abs=2e-3)
    total = red + res[d]["catch"]
    regrown = cm["game"]["G"] - (G0 - total)
    assert regrown >= 0                                                       # the catch left the game stock, then it regrew
    assert not any(ev["type"] == "camp_round" and "hunt" in ev["data"]["text"] for ev in k.events)   # results are private
    hr = [ev for ev in k.events if ev["type"] == "hunt_round"]
    assert len(hr) == 1 and hr[0]["vis"] == "monitor" and not k.can_see(e, hr[0])
    assert {(p["party"], tuple(p["hunters"]), p["catch"]) for p in hr[0]["data"]["parties"]} == \
        {("red", tuple(sorted([a, b, c])), red), (None, (d,), res[d]["catch"])}
    assert not cm["hunts"]                                                    # entries are for one round
    assert not [ev for ev in k.events if ev["type"] == "hunt" and k.can_see(e, ev)]   # sealed: only the hunter sees its entry


def test_the_hunt_is_deterministic_and_draws_its_own_stream():
    def run():
        inst, k = small(["subsistence.spoil=0", "subsistence.ration=0"])
        f, cm = forest(k)
        out = []
        for r in range(4):
            for i, x in enumerate(eaters(k)[:6]):
                A.act(k, x, "hunt", {"camp": f, "party": f"p{i % 2}"})
            end_round(k)
            out.append((round(cm["game"]["G"], 4), round(cm["S"], 4)))
        return out
    assert run() == run()


def test_game_regrows_logistically_with_inflow_and_an_optional_allee_threshold():
    inst, k = small(["subsistence.seasons.enabled=false"])
    f, cm = forest(k)
    K = cm["game"]["K"]
    cm["game"]["G"] = 0.5 * K
    end_round(k)
    assert cm["game"]["G"] == pytest.approx(0.5 * K + 0.2 * 0.5 * K * 0.5 + 0.01 * 0.5 * K, abs=1e-3)
    cm["game"]["G"] = 0.0
    end_round(k)
    assert cm["game"]["G"] == pytest.approx(0.01 * K, abs=1e-3)             # animals walk in from the land around
    inst, k = small(["subsistence.seasons.enabled=false", "subsistence.game={allee: 0.2, inflow: 0}"])
    f, cm = forest(k)
    K = cm["game"]["K"]
    cm["game"]["G"] = 0.1 * K
    end_round(k)
    assert cm["game"]["G"] < 0.1 * K                                         # below the threshold the herd shrinks
    cm["game"]["G"] = 0.6 * K
    end_round(k)
    assert cm["game"]["G"] > 0.6 * K


def test_plants_regrow_logistically_and_seasons_move_their_rate():
    inst, k = small(["subsistence.seasons.enabled=false"])
    f, cm = forest(k)
    assert cm["r"] == pytest.approx(0.6) and SB.season_name(k) == "normal"
    cm["S"] = 0.5 * cm["K"]
    end_round(k)
    assert cm["S"] == pytest.approx(0.5 * cm["K"] * (1 + 0.6 * 0.5), abs=1e-3)
    inst, k = small()
    f, cm = forest(k)
    seen = []
    for _ in range(30):
        seen.append(SB.season_name(k))
        want = {"lean": 0.6, "normal": 1.0, "plentiful": 1.3}[seen[-1]] * 0.6
        assert cm["r"] == pytest.approx(want)
        end_round(k)
    assert set(seen) == {"lean", "normal", "plentiful"}
    runs = sum(1 for x, y in zip(seen, seen[1:]) if x == y)
    assert runs >= 10                                                         # persistence: seasons often last
    inst2, k2 = small()
    seen2 = []
    for _ in range(30):
        seen2.append(SB.season_name(k2))
        end_round(k2)
    assert seen2 == seen                                                      # its own stream: the same seed, the same seasons
    log = SB.state(k)["log"][-1]
    assert set(log["forests"]) == {f} and log["season"] in ("lean", "normal", "plentiful")


def test_agents_see_plants_coarse_game_and_the_season():
    from charter.camptypes import framework as CT
    inst, k = small()
    f, cm = forest(k)
    a = eaters(k)[0]
    line = CT.view(k, f, fresh=False).state_line(k, a)
    assert line.startswith("plants 95% of capacity") and "game plentiful" in line and "season " in line
    cm["game"]["G"] = 0.05 * cm["game"]["K"]
    assert "game very scarce" in CT.view(k, f, fresh=False).state_line(k, a)
    assert str(round(cm["game"]["G"], 1)) not in line
    from charter.camptypes import forest as FO
    assert [FO.game_level(x) for x in (0.9, 0.45, 0.2, 0.05)] == ["plentiful", "fair", "scarce", "very scarce"]


CLOSED_SEASON = '''title = "Closed Season"
intent = "No hunting while game is scarce."
def before_hunt(p, chain):
    if forest(p["camp"])["game"] in ("scarce", "very scarce"):
        return False
'''


def test_a_law_closes_the_hunt_when_game_is_scarce():
    inst, k = world("society", ["subsistence.enabled=true", "law.v2=true"], constitution=True)
    k.enact(k.new_law(CLOSED_SEASON, "closed"))
    a = eaters(k)[0]
    f, cm = forest(k)
    assert A.act(k, a, "hunt", {"camp": f}).startswith("You hunt")
    cm["game"]["G"] = 0.2 * cm["game"]["K"]
    b = eaters(k)[1]
    with pytest.raises(A.ActionError, match="a law blocked this hunt"):
        A.act(k, b, "hunt", {"camp": f})
    assert b not in cm["hunts"] and SB.state(k)["forage"].get(b, 0) == 0     # nothing entered, no forest action used
    api = k.api_for(next(iter(k.w["laws"])))
    assert api["forest"](f)["game"] == "scarce" and api["forest"]("camp1") is None
    p = PR.get("hunt")
    assert p.tier == "L" and p.routed and p.before and PR.ACTION_PRIMITIVES["hunt"][0] == "hunt"


def test_world_events_never_destroy_or_blight_a_forest():
    import random as _r
    from charter import events as EV
    inst, k = small()
    f, cm = forest(k)
    for i in range(40):
        EV.h_camp_destroyed(k, inst, {"rng": _r.Random(i), "cfg": {"min_camps": 0}})
        EV.h_camp_blight(k, inst, {"rng": _r.Random(i), "cfg": {}, "id": "E1"})
    assert cm.get("destroyed") is None and not cm.get("blight") and f in SB.forest_camps(k)


def test_the_bot_hunts_in_bands_and_forages_when_short():
    inst, k = small(["subsistence.bot_hunt=1.0", "subsistence.bot_effort=2"])
    f, cm = forest(k)
    a = eaters(k)[0]
    acts = SB.scripted_actions(k, a, 5)
    hunts = [json.loads(x["args_json"]) for x in acts if x["action"] == "hunt"]
    assert len(hunts) == 2 and hunts[0] == {"camp": f, "party": "band0"}
    set_food(k, a, 0.5)
    acts = SB.scripted_actions(k, a, 5)
    assert [x["action"] for x in acts][:2] == ["harvest", "harvest"] and "hunt" not in [x["action"] for x in acts]   # short: gather
    inst, k = small(["subsistence.bot_hunt=0"])
    a = eaters(k)[0]
    set_food(k, a, 0.5)
    assert [x["action"] for x in SB.scripted_actions(k, a, 5)][:2] == ["harvest", "harvest"]
    cm2 = forest(k)[1]
    cm2["destroyed"] = 0                                                      # no forest left: the bot does not crash
    assert all(x["action"] != "harvest" for x in SB.scripted_actions(k, a, 5))


def test_overhunting_empties_the_forest_and_restraint_keeps_it():
    def game_after(hunters, rounds=12):
        inst, k = small(["subsistence.seasons.enabled=false", "subsistence.ration=0"])
        f, cm = forest(k)
        for _ in range(rounds):
            for i, x in enumerate(eaters(k)[:hunters]):
                for _e in range(2):
                    A.act(k, x, "hunt", {"camp": f, "party": f"p{i % 2}"})
            end_round(k)
        return cm["game"]["G"] / cm["game"]["K"]
    assert game_after(8) < 0.35 < game_after(1)


# ---------------------------------------------------------------------- S3: stores
def builder(k, aid):
    k._add(aid, "timber", 10)
    k._add(aid, "stone", 6)


def test_building_a_store_costs_its_materials_and_makes_an_account():
    inst, k = small()
    a, b = eaters(k)[:2]
    for x in (a, b):
        for i in ("timber", "stone"):
            k.w["agents"][x]["holdings"].pop(i, None)
    with pytest.raises(A.ActionError, match="a store costs 10 timber, 6 stone"):
        A.act(k, a, "build", {"kind": "store"})
    builder(k, a)
    t0, s0 = k.bal(a, "timber"), k.bal(a, "stone")
    assert A.act(k, a, "build", {"kind": "store"}).startswith("Built store S1")
    assert k.bal(a, "timber") == pytest.approx(t0 - 10) and k.bal(a, "stone") == pytest.approx(s0 - 6)
    assert AC.kind_of(k, "store:S1") == "store" and "store:S1" in AC.keys(k)
    assert SB.state(k)["stores"]["S1"]["owner"] == a and any(e["type"] == "store_built" and e["vis"] == "public" for e in k.events)
    with pytest.raises(A.ActionError, match="irrigation"):
        A.act(k, a, "build", {"kind": "irrigation"})
    SB.state(k)["stage"][b] = -1
    builder(k, b)
    with pytest.raises(A.ActionError, match="you are hungry: build needs you fed"):
        A.act(k, b, "build", {"kind": "store"})


def test_anyone_deposits_only_the_owner_withdraws_and_capacity_holds():
    inst, k = small()
    a, b = eaters(k)[:2]
    builder(k, a)
    A.act(k, a, "build", {"kind": "store"})
    set_food(k, b, 50)
    assert A.act(k, b, "transfer", {"to": "store:S1", "item": "food", "qty": 30}).startswith("Put 30 food in store S1")
    with pytest.raises(A.ActionError, match="holds at most 40 food"):
        A.act(k, b, "transfer", {"to": "store:S1", "item": "food", "qty": 11})
    k._add(a, "stone", 1)
    with pytest.raises(A.ActionError, match="holds food only"):
        A.act(k, a, "transfer", {"to": "store:S1", "item": "stone", "qty": 1})
    with pytest.raises(A.ActionError, match="only its owner"):
        A.act(k, b, "withdraw", {"store": "S1", "qty": 1})
    f0 = k.bal(a, "food")
    assert A.act(k, a, "withdraw", {"store": "S1", "qty": 5}).startswith("Took 5 food from store S1")
    assert k.bal(a, "food") - f0 == pytest.approx(5) and k.bal("store:S1", "food") == pytest.approx(25)
    with pytest.raises(A.ActionError, match="holds only 25"):
        A.act(k, a, "withdraw", {"store": "S1", "qty": 26})
    assert any(x.startswith("Your stores: S1 25/40 food") for x in SB.state_lines(k, a))


def test_store_spoilage_is_slower():
    inst, k = small(["subsistence.ration=0"])
    a = eaters(k)[0]
    builder(k, a)
    A.act(k, a, "build", {"kind": "store"})
    set_food(k, a, 30)
    A.act(k, a, "transfer", {"to": "store:S1", "item": "food", "qty": 20})
    end_round(k)
    assert k.bal("store:S1", "food") == pytest.approx(20 * 0.98) and k.bal(a, "food") == pytest.approx(10 * 0.85)


def test_a_law_cannot_take_from_a_store_it_does_not_own():
    from charter import lawlang as L
    inst, k = small()
    a = eaters(k)[0]
    builder(k, a)
    A.act(k, a, "build", {"kind": "store"})
    k._add("store:S1", "food", 10)
    with pytest.raises(L.LawError, match="only its owner"):
        k.apply("move", src="store:S1", dst=a, item="food", qty=1, why="law:L9")
    with pytest.raises(L.LawError, match="only its owner"):
        k.apply("move", src="store:S1", dst=a, item="food", qty=1, why="transfer")


ASSOC_CODE = '''title = "Granary Club"
intent = "Members' granary: the store feeds members who hold less than a meal."
def on_round_end(r):
    for m in members():
        if food_of(m) < 1:
            move("store:S1", m, "food", 1)
'''


def test_an_institution_owns_a_store_and_its_law_moves_food_out():
    inst, k = world("society", ["subsistence.enabled=true", "law.v2=true", "contracts.enabled=true"], constitution=True)
    a, b, c = eaters(k)[:3]
    A.act(k, a, "create_contract", {"name": "Granary Club", "code": ASSOC_CODE})
    cid = next(iter(AC.assocs(k)))
    A.act(k, b, "join_contract", {"contract": cid})
    builder(k, a)
    builder(k, c)
    with pytest.raises(A.ActionError, match="member or officer"):
        A.act(k, c, "build", {"kind": "store", "owner": cid})
    assert A.act(k, a, "build", {"kind": "store", "owner": cid}).startswith("Built store S1")
    assert SB.state(k)["stores"]["S1"]["owner"] == cid
    k._add("store:S1", "food", 1)
    with pytest.raises(A.ActionError, match="only its officers may"):
        A.act(k, a, "withdraw", {"store": "S1", "qty": 1})                 # the founder is not an officer: only its code takes out
    set_food(k, c, 20)
    A.act(k, c, "transfer", {"to": "store:S1", "item": "food", "qty": 10})  # anyone deposits
    set_food(k, b, 0)
    end_round(k)
    assert SB.stage(k, b) == 0                                             # fed from the granary before the ration
    assert k.bal("store:S1", "food") < 10 * 0.98 + 1e-6                    # (and spoiled at 2%)


MEMBERS_TAKE = '''title = "Members' Granary"
intent = "Any member may take food out of the club's store; nobody else."
def before_withdraw(p, chain):
    return p["agent"] in members()
'''


def granary(code, monkeypatch=None, officers=()):
    inst, k = world("society", ["subsistence.enabled=true", "law.v2=true", "contracts.enabled=true"], constitution=True)
    a, b, c = eaters(k)[:3]
    A.act(k, a, "create_contract", {"name": "Granary", "code": code})
    cid = next(iter(AC.assocs(k)))
    A.act(k, b, "join_contract", {"contract": cid})
    builder(k, a)
    A.act(k, a, "build", {"kind": "store", "owner": cid})
    k._add("store:S1", "food", 10)
    if monkeypatch is not None:
        from charter import institutions as I
        monkeypatch.setattr(I, "officers", lambda k_, iid: list(officers) if iid == cid else [])
    return inst, k, cid, (a, b, c)


def test_withdrawal_from_an_institution_store_is_the_institutions_to_decide(monkeypatch):
    inst, k, cid, (a, b, c) = granary(ASSOC_CODE, monkeypatch, officers=("__nobody__",))
    for x in (a, b, c):                                                   # its code says nothing: officers only (the residual)
        with pytest.raises(A.ActionError, match="only its officers may"):
            A.act(k, x, "withdraw", {"store": "S1", "qty": 1})
    monkeypatch.setattr(__import__("charter.institutions", fromlist=["x"]), "officers", lambda k_, iid: [c] if iid == cid else [])
    assert A.act(k, c, "withdraw", {"store": "S1", "qty": 1}).startswith("Took 1 food")   # an officer, even a non-member
    assert any(e["type"] == "store_withdrawal" and e["data"]["owner"] == cid for e in k.events)
    inst, k, cid, (a, b, c) = granary(MEMBERS_TAKE, monkeypatch, officers=(c,))
    assert A.act(k, b, "withdraw", {"store": "S1", "qty": 2}).startswith("Took 2 food")   # the code admits a member
    with pytest.raises(A.ActionError, match="a law blocked this withdrawal"):
        A.act(k, c, "withdraw", {"store": "S1", "qty": 1})                 # ...and refuses everyone else, its officer too
    assert k.bal("store:S1", "food") == pytest.approx(8)
    names = [x.name for x in AR.available(inst, k, k.agent(b))]
    assert "withdraw" in names                                             # members are offered withdraw (their code may let them)
    p = PR.get("withdraw")
    assert p.tier == "L" and p.routed and p.before and p.blockable and PR.ACTION_PRIMITIVES["withdraw"][0] == "withdraw"


def test_an_agents_store_is_its_owners_without_law():
    inst, k = small()                                                      # no law.v2: the residual alone decides
    a, b = eaters(k)[:2]
    builder(k, a)
    A.act(k, a, "build", {"kind": "store"})
    k._add("store:S1", "food", 4)
    with pytest.raises(A.ActionError, match="only its owner"):
        A.act(k, b, "withdraw", {"store": "S1", "qty": 1})
    with pytest.raises(__import__("charter.dispatch", fromlist=["x"]).Blocked, match="only its owner"):
        k.apply("withdraw", agent=b, store="S1", owner=a, qty=1)           # the primitive's residual, called directly
    assert A.act(k, a, "withdraw", {"store": "S1", "qty": 1}).startswith("Took 1 food")


def test_a_dead_owners_store_passes_on():
    inst, k = small()
    a = eaters(k)[0]
    builder(k, a)
    A.act(k, a, "build", {"kind": "store"})
    assert MO.disable(k, a, "accident")
    assert SB.state(k)["stores"]["S1"]["owner"] == "J0" and any(e["type"] == "store_owner" for e in k.events)


def test_stores_conserve_food():
    inst, k = small(["subsistence.ration=0", "subsistence.spoil=0", "subsistence.store_spoil=0"])
    a, b = eaters(k)[:2]
    builder(k, a)
    A.act(k, a, "build", {"kind": "store"})
    t0 = AC.totals(k)["food"]
    A.act(k, b, "transfer", {"to": "store:S1", "item": "food", "qty": 2})
    A.act(k, a, "withdraw", {"store": "S1", "qty": 1})
    end_round(k)
    assert AC.totals(k)["food"] == pytest.approx(t0)


def test_a_minor_forages_and_hunts_at_half(monkeypatch):
    from charter import pairs as PRS
    inst, k = small()
    a, b = eaters(k)[:2]
    assert SB.yield_mult(k, a) == 1.0                                         # no pairs: no minors
    k.w.setdefault("life", {}).setdefault("pairs", {})
    monkeypatch.setattr(PRS, "is_minor", lambda k_, x: x == a)
    assert SB.yield_mult(k, a) == 0.5 and SB.yield_mult(k, b) == 1.0
    SB.state(k)["stage"][a] = -1
    assert SB.yield_mult(k, a) == pytest.approx(0.375)                       # hungry minor: x0.75 x0.5


def test_a_rare_forest_shock_strips_a_stock_and_tells_the_users():
    assert SB.DEFAULTS["forest"]["shock"] == {"p": 0.02, "loss": [0.3, 0.6]}
    inst, k = small(["subsistence.forest.shock.p=1.0", "subsistence.game.regrowth=0", "subsistence.game.inflow=0"])
    f, cm = forest(k)
    a, b = eaters(k)[:2]
    k.begin_round_cause(k.r, "round_start")
    k.start_round()
    A.act(k, a, "harvest", {"camp": f})                                      # a used the forest this round; b did not
    G0 = cm["game"]["G"]
    k.phase("end_of_round")
    k.end_round()
    k.end_round_cause()
    ev = [e for e in k.events if e["type"] == "forest_shock"]
    assert len(ev) == 1 and ev[0]["data"]["users"] == [a] and k.can_see(a, ev[0]) and not k.can_see(b, ev[0])
    d = ev[0]["data"]
    assert 0.3 <= d["loss"] <= 0.6
    if d["stock"] == "game":
        assert d["before"] == pytest.approx(G0) and cm["game"]["G"] == pytest.approx(G0 * (1 - d["loss"]), abs=1e-3)
    else:
        assert cm["S"] == pytest.approx(d["before"] * (1 - d["loss"]), abs=1e-3)
    inst, k = small()                                                        # the default: rare (2% a forest a round)
    for _ in range(10):
        end_round(k)
    assert sum(e["type"] == "forest_shock" for e in k.events) <= 2


NO_FORAGE = '''title = "No Forage"
intent = "No foraging."
def before_harvest(p, chain):
    return False
'''


def test_a_blocked_forage_takes_no_fee(monkeypatch):
    from charter import jurisdictions as J
    for blocked in (True, False):
        inst, k = world("society", ["subsistence.enabled=true", "law.v2=true"], constitution=True)
        if blocked:
            k.enact(k.new_law(NO_FORAGE, "noforage"))
        a, b = eaters(k)[:2]
        f = food_camps(k, "forest")[0]
        monkeypatch.setattr(J, "camp_rules", lambda k_, aid, camp: {"quota": None, "harvest_limit": None, "qkey": f"x|{camp}",
                                                                     "fee": {"item": "food", "qty": 1.0}, "reserve": b})
        set_food(k, a, 3)
        set_food(k, b, 0)
        if blocked:
            with pytest.raises(Exception, match="block|refus"):
                A.act(k, a, "harvest", {"camp": f})
            assert k.bal(a, "food") == pytest.approx(3) and k.bal(b, "food") == pytest.approx(0)   # no fee taken
            assert not SB.state(k)["forage"].get(a)
        else:
            A.act(k, a, "harvest", {"camp": f})
            assert k.bal(b, "food") == pytest.approx(1)                     # the fee, paid once the forage went through
        monkeypatch.undo()


def test_scripted_bots_propose_no_harvest_levies_or_quotas():
    import json
    from charter import library as LB
    from charter.agents import ScriptedPolicy
    inst, k = small()
    a = eaters(k)[0]
    act = lambda _a, **kw: {"action": _a, "args_json": json.dumps(kw)}
    levy, quotas = LB.code("Harvest Levy", inst), LB.code("Harvest Quotas", inst)
    harmless = 'title = "Gazette"\nintent = "x"\ndef on_round_start(r):\n    pass\n'
    acts = [act("propose", code=levy), act("propose", code=quotas), act("create_contract", name="c", template="company"),
            act("create_contract", name="d", template="cartel"), act("propose", code=harmless), act("hunt", camp="x")]
    assert [json.loads(x["args_json"]).get("code", x["action"]) for x in SB.bot_filter(k, acts)] == [harmless, "hunt"]
    off_inst, off = world("nature_design", [SMALL])
    assert SB.bot_filter(off, acts) == acts                                   # subsistence off: untouched
    from charter import context as CX
    inst, k = world("society", ["subsistence.enabled=true"], constitution=True)
    a = eaters(k)[0]
    k.inst["library"] = ["Harvest Levy", "Harvest Quotas"]                    # a legislator bot drawing from the library
    k.w["agents"][a]["cls"] = "legislator"
    k.w["agents"][a]["rights"].append("propose")
    pol = ScriptedPolicy(1)
    acts = [x["action"] for _ in range(20)
            for x in pol.act(k, {**k.w["agents"][a], "id": a}, "", CX.FETCHED_HEADER, 6, False)[0]["actions"]]
    assert "hunt" in acts and "propose" not in acts                          # (86 proposals in these 20 turns without the filter)


def test_the_island_preset_lets_game_go_extinct():
    sp = S.load("island_subsistence")
    c = SB.cfg(sp)
    assert SB.enabled(sp) and c["game"]["allee"] > 0 and c["game"]["inflow"] == 0
    assert c["forest"] == SB.cfg(S.load("nature_subsistence"))["forest"]      # otherwise as nature_subsistence
    inst, k = world("island_subsistence", [SMALL, "subsistence.forest.shock.p=0"], rounds=40)
    f, cm = forest(k)
    cm["game"]["G"] = 0.1 * cm["game"]["K"]                                  # overhunted below the threshold: no recovery
    for _ in range(30):
        end_round(k)
    assert cm["game"]["G"] < 0.05 * cm["game"]["K"]                          # shrinking toward zero with no hunting at all
    inst, k = small(["subsistence.forest.shock.p=0"], rounds=40)            # the mainland: animals walk in, the game recovers
    f, cm = forest(k)
    cm["game"]["G"] = 0.1 * cm["game"]["K"]
    for _ in range(30):
        end_round(k)
    assert cm["game"]["G"] > 0.5 * cm["game"]["K"]
