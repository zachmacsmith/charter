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


# ---------------------------------------------------------------------- S2: the composer and the food camps
def food_camps(k, typ):
    return [cid for cid, c in sorted(k.w["camps"].items()) if c.get("role") == "subsistence" and c["type"] == typ]


def test_the_composer_appends_food_camps_and_draws_nothing_else():
    for seed in range(1, 21):
        sets = ["shared_archive.enabled=false", SMALL]
        off = generator.generate(S.apply_overrides(S.load("nature_design"), sets), seed)
        on = generator.generate(S.apply_overrides(S.load("nature_subsistence"), sets), seed)
        n = len(off["camps"])
        assert on["camps"][:n] == off["camps"] and all(c["type"] not in ("forest", "fields") for c in off["camps"])
        assert [c["type"] for c in on["camps"][n:]] == ["forest", "fields", "weak_link"]
        assert all(c["role"] == "subsistence" and c["resource"] == "food" and c["open"] for c in on["camps"][n:])
        assert on["spec"]["unit_values"]["food"] == 1.0 and "food" not in off["spec"]["unit_values"]
        assert [a["rights"] for a in on["agents"]] == [a["rights"] for a in off["agents"]]
    inst = generator.generate(S.apply_overrides(S.load("nature_subsistence"), [
        "shared_archive.enabled=false", "agents={worker: 100, scientist: 0, legislator: 0, media: 0, board: 0, fixer: 1}"]), 1)
    types = [c["type"] for c in inst["camps"] if c.get("role") == "subsistence"]
    assert types.count("forest") == 4 and types.count("fields") == 3 and types.count("weak_link") == 1
    assert sum(len(c["plots"]) for c in inst["camps"] if c["type"] == "fields") == 40


def test_food_camps_ignore_open_classes():
    inst, k = world("society", ["subsistence.enabled=true"])
    assert k.spec["camps"]["typed"]["open_classes"] == ["worker"]
    leg = next(a for a in eaters(k) if k.w["agents"][a]["cls"] == "legislator")
    social = next(cid for cid, c in k.w["camps"].items() if c.get("role") == "social")
    with pytest.raises(A.ActionError, match="Workers only"):
        A.act(k, leg, "harvest", {"camp": social, "x": [1]})
    assert A.act(k, leg, "harvest", {"camp": food_camps(k, "forest")[0]}).startswith("Foraged")
    assert A.act(k, leg, "farm", {"camp": food_camps(k, "fields")[0], "sow": 1}).startswith("Sowed 1 food")
    board = next(a for a, v in k.w["agents"].items() if v["cls"] == "board")
    with pytest.raises(A.ActionError):
        A.act(k, board, "harvest", {"camp": food_camps(k, "forest")[0]})


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


def test_a_law_quota_applies_to_foraging():
    inst, k = small()
    a, b = eaters(k)[:2]
    f = food_camps(k, "forest")[0]
    k.w["camps"][f]["quota"] = 1
    A.act(k, a, "harvest", {"camp": f})
    with pytest.raises(A.ActionError, match="quota"):
        A.act(k, b, "harvest", {"camp": f})


def test_felling_shrinks_the_forest_and_clears_a_plot():
    inst, k = small()
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


def test_sow_ripen_reap_by_another_and_the_sower_is_told():
    inst, k = small(["subsistence.spoil=0", "subsistence.fields={blight: 0, noise: 0}"])
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
    inst, k = small()
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
    inst, k = small(["subsistence.fields={blight: 0, noise: 0, grow: 1}"])
    a = eaters(k)[0]
    fl = food_camps(k, "fields")[0]
    set_food(k, a, 3)
    A.act(k, a, "farm", {"camp": fl, "sow": 2})
    end_round(k)
    p = k.w["camps"][fl]["plots"][0]
    assert p["status"] == "ripe" and p["left"] == 1.0
    end_round(k)
    assert p["left"] == pytest.approx(0.5)                                  # unreaped through its first ripe round
    inst, k = small(["subsistence.fields={blight: 1}"])
    a = eaters(k)[0]
    fl = food_camps(k, "fields")[0]
    A.act(k, a, "farm", {"camp": fl, "sow": 1})
    for _ in range(3):
        end_round(k)
    assert k.w["camps"][fl]["plots"][0]["status"] == "fallow" and any(e["type"] == "crop_failed" for e in k.events)


def test_the_hunt_pays_a_party_far_more_than_a_lone_hunter():
    inst, k = small(["subsistence.spoil=0", "subsistence.ration=0"])
    a, b, c = eaters(k)[:3]
    h = food_camps(k, "weak_link")[0]
    assert "hunt" in SB.rules_text(inst) and k.w["camps"][h]["open"]
    f = {x: k.bal(x, "food") for x in (a, b, c)}
    A.act(k, a, "harvest", {"camp": h, "x": [10]})
    A.act(k, b, "harvest", {"camp": h, "x": [10]})
    end_round(k)
    assert k.bal(a, "food") - f[a] == pytest.approx(2.0) and k.bal(b, "food") - f[b] == pytest.approx(2.0)
    f = {x: k.bal(x, "food") for x in (a, b, c)}
    A.act(k, c, "harvest", {"camp": h, "x": [0]})
    end_round(k)
    assert k.bal(c, "food") - f[c] == pytest.approx(0.4)


TILLERS = '''title = "Tillers' Right"
intent = "Only the sower of a crop may reap it."
def before_reap(p, chain):
    for pl in plots(p["camp"]):
        if pl["id"] == p["plot"] and pl["sower"] != None and pl["sower"] != p["agent"]:
            return False
'''


def test_a_tillers_right_law_refuses_a_non_sower():
    inst, k = world("society", ["subsistence.enabled=true", "law.v2=true", "subsistence.fields={grow: 1, blight: 0}"],
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
    assert "camp6 food (open forest: forage food" in core and "[manual: Food]" in core and "farm (sow food" in core
    assert "Food. Every agent" in json.dumps(CX.build_manual(inst, k, a["id"]))
    inst, k = world("nature_design", [SMALL])
    core = CX.core_prompt(inst, next(x for x in inst["agents"] if x["cls"] != "fixer"), k)
    assert "food" not in core.lower() and "farm (" not in core


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
    with pytest.raises(A.ActionError, match="only its owner"):
        A.act(k, a, "withdraw", {"store": "S1", "qty": 1})                 # the founder is not an officer: only its code takes out
    set_food(k, c, 20)
    A.act(k, c, "transfer", {"to": "store:S1", "item": "food", "qty": 10})  # anyone deposits
    set_food(k, b, 0)
    end_round(k)
    assert SB.stage(k, b) == 0                                             # fed from the granary before the ration
    assert k.bal("store:S1", "food") < 9 * 0.98 + 1e-6                     # (and spoiled at 2%)


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
