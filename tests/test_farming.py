"""Farming (engine 14; docs/review/31_institutions/01b_farming.md): farms and holdings, start.farms, tending, improvements and their
upkeep, skills, the plough, clearing forest into plots, crop shocks, the individual hunt, and the worlds that must not change
(fields off; the shared hunt; runs of earlier engines under their frozen settings). No model calls."""
from __future__ import annotations

import json
import random

import pytest

from charter import action_registry as AR
from charter import actions as A
from charter import generator
from charter import spec as S
from charter import subsistence as SB
from charter.camptypes import fields as FL
from charter.camptypes import forest as FO
from charter.kernel import Kernel

SMALL = "agents={worker: 8, scientist: 0, legislator: 0, media: 0, board: 0, fixer: 1}"
FIELDS = "subsistence.fields.enabled=true"


def world(preset="nature_subsistence", extra=(), seed=3, rounds=12):
    sp = S.apply_overrides(S.load(preset), [f"rounds={rounds}", "shared_archive.enabled=false", *extra])
    inst = generator.generate(sp, seed)
    return inst, Kernel(inst)


def small(extra=(), **kw):
    return world(extra=(SMALL, FIELDS, "subsistence.spoil=0", *extra), **kw)


def setup(inst, k):
    """The start block's round-0 entries, as the runner applies them (charter/start.py)."""
    from charter import start as STT
    for e in STT.schedule(inst):
        STT.HANDLERS[e["args"]["kind"]](k, inst, e["args"]["spec"])
    return k


def end_round(k):
    k.begin_round_cause(k.r, "round_start")
    k.start_round()
    k.phase("end_of_round")
    k.end_round()
    k.end_round_cause()


def fields(k):
    return SB.fields_camps(k)[0]


def set_food(k, aid, q):
    k.w["agents"][aid]["holdings"].pop("food", None)
    if q:
        k.w["agents"][aid]["holdings"]["food"] = float(q)


def give(k, aid, **items):
    for i, q in items.items():
        k._add(aid, i, float(q))


def plot(k, cid, pid):
    return FL._plot(k.w["camps"][cid], pid)


def ripen(k, cid, pid, noise=0.0):
    """Make plot pid's crop ripe now, with no noise (the tests read exact yields)."""
    pl = plot(k, cid, pid)
    pl.update({"status": "ripe", "ripe": k.r, "noise": noise})
    return pl


# ---------------------------------------------------------------------- fields off: nothing changes
def test_fields_off_no_farming_action_or_word():
    from charter import context as CX
    inst, k = world(extra=(SMALL,))
    a = next(x for x in inst["agents"] if x["cls"] != "fixer")
    assert not SB.fields_camps(k)
    avail = [x.name for x in AR.available(inst, k, a)]
    for name in ("farm", "tend", "improve", "practice", "clear"):
        assert name not in avail
        with pytest.raises(A.ActionError, match=f"unknown action '{name}'"):
            A.act(k, a["id"], name, {"camp": "camp6"})
    text = SB.rules_text(inst) + CX.core_prompt(inst, a, k)
    for word in ("farm", "plot", "tend {", "clear {"):
        assert word not in text, word
    assert "keeps its own catch" in SB.rules_text(inst)                   # engine 14: the hunt's text follows its mode
    from charter import agents as AG
    assert "draws its own catch" in AG.action_doc("hunt", inst, a)
    inst2, _ = world(extra=(SMALL, "subsistence.game.hunt_mode=shared"))
    assert AG.action_doc("hunt", inst2, a).endswith("a party of 3 to 6 has good chances of a deer or a large animal, shared by effort")
    assert "share one quarry more thinly, and fewer animals mean fewer kills" in SB.rules_text(inst2)   # the engine 13 text


def test_start_farms_need_fields_and_resolve(tmp_path):
    import yaml
    p = tmp_path / "w.yaml"
    p.write_text(yaml.safe_dump({"extends": ["nature_farming"], "subsistence": {"fields": {"enabled": False}}}))
    with pytest.raises(ValueError, match="farms need fields"):
        generator.generate(S.load(str(p)), 1)
    p.write_text(yaml.safe_dump({"extends": ["nature_farming"], "start": {"farms": [{"owner": "Alder", "plots": 30}]}}))
    with pytest.raises(ValueError, match="too few plots"):
        generator.generate(S.load(str(p)), 1)
    p.write_text(yaml.safe_dump({"extends": ["nature_farming"], "start": {"farms": [{"owner": "Nobody", "plots": 1}]}}))
    with pytest.raises((ValueError, SystemExit), match="Nobody"):
        generator.generate(S.load(str(p)), 1)
    from charter import schema as SC
    errs = SC.validate(S.set_path(S.load("nature_farming"), "start", {"farms": [{"owner": "Alder", "plots": 0, "works": {"x": 1}}]}))
    assert any("plots: a whole number" in e for e in errs) and any("works:" in e for e in errs)


# ---------------------------------------------------------------------- start.farms: farmers from round 0
def test_start_farms_hold_plots_with_crops_from_round_0():
    inst, k = world("nature_farming", rounds=8, seed=1)
    setup(inst, k)
    fl = fields(k)
    c = k.w["camps"][fl]
    assert len(c["plots"]) == 24                                          # one fields camp, plots_per_agent 1.0 x 24
    held = {}
    for p in c["plots"]:
        held.setdefault(p["holder"], []).append(p["id"])
    assert held == {"Alder": [1, 2, 3], "Bryn": [4, 5, 6], "Cass": [7, 8, 9], "Dell": [10, 11, 12], "Edda": [13, 14, 15],
                    "Fion": [16, 17, 18], None: [19, 20, 21, 22, 23, 24]}
    assert [plot(k, fl, i)["status"] for i in (1, 2, 3)] == ["growing"] * 3
    assert [plot(k, fl, i)["ripe"] for i in (1, 2, 3)] == [1, 2, 3]        # ripening in turn: a harvest from round 2 on
    assert all(plot(k, fl, i)["seed"] == 3 and plot(k, fl, i)["sower"] == "Alder" for i in (1, 2, 3))
    assert any(e["type"] == "farm_held" and e["vis"] == "public" and e["data"]["holder"] == "Alder" for e in k.events)
    lines = SB.state_lines(k, "Alder")
    assert any(x.startswith(f"Your farm at {fl}") and "plot 1 growing, ripe in round 2" in x and "(tend it: +15%)" in x for x in lines)
    assert not any("Your farm" in x for x in SB.state_lines(k, "Gale"))
    assert "Farms." in SB.rules_text(inst) and "tend {" in SB.rules_text(inst)
    end_round(k)
    assert plot(k, fl, 1)["status"] == "ripe" and plot(k, fl, 2)["status"] == "growing"
    assert any("plot 1 RIPE" in x for x in SB.state_lines(k, "Alder"))


# ---------------------------------------------------------------------- holdings: who may work a farm
def test_holdings_are_respected_and_open_plots_stay_open():
    inst, k = small()
    fl = fields(k)
    a, b, c = SB.eaters(k)[:3]
    FL.establish(k, a, fl, 2, crops=False)                                # plots 1, 2 are a's farm; the rest open
    for x in (a, b, c):
        set_food(k, x, 10)
    with pytest.raises(A.ActionError, match=f"is {a}'s farm"):
        A.act(k, b, "farm", {"camp": fl, "sow": 2, "plot": 1})
    assert "plot 3" in A.act(k, b, "farm", {"camp": fl, "sow": 2})        # no plot named: the first open one
    assert "plot 1" in A.act(k, a, "farm", {"camp": fl, "sow": 3})        # the holder: its own first
    with pytest.raises(A.ActionError, match=f"is {a}'s farm"):
        A.act(k, b, "tend", {"camp": fl, "plot": 1})
    A.act(k, a, "farm", {"camp": fl, "allow": b})
    assert A.act(k, b, "tend", {"camp": fl, "plot": 1}).startswith(f"Tended {fl} plot 1")
    ripen(k, fl, 1)
    with pytest.raises(A.ActionError, match=f"is {a}'s farm"):
        A.act(k, c, "farm", {"camp": fl, "reap": 1})
    fa, fb = k.bal(a, "food"), k.bal(b, "food")
    out = A.act(k, b, "farm", {"camp": fl, "reap": 1})                    # a hand reaps: the crop is the farm's (share 1)
    y = 3 * 3.0 * 1.15
    assert f"went to the farm's holder {a}" in out
    assert k.bal(a, "food") - fa == pytest.approx(y, abs=1e-3) and k.bal(b, "food") == pytest.approx(fb)
    ev = [e for e in k.events if e["type"] == "reap"][-1]
    assert set(ev["vis"]) == {a, b} and ev["data"]["to_holder"] == pytest.approx(y, abs=1e-3)
    A.act(k, a, "farm", {"camp": fl, "share": 0.5})                       # sharecropping
    A.act(k, a, "farm", {"camp": fl, "sow": 2, "plot": 2})
    ripen(k, fl, 2)
    fa, fb = k.bal(a, "food"), k.bal(b, "food")
    A.act(k, b, "farm", {"camp": fl, "reap": 2})
    assert k.bal(a, "food") - fa == pytest.approx(3.0, abs=1e-3) and k.bal(b, "food") - fb == pytest.approx(3.0, abs=1e-3)
    A.act(k, a, "farm", {"camp": fl, "disallow": b})
    with pytest.raises(A.ActionError, match=f"is {a}'s farm"):
        A.act(k, b, "farm", {"camp": fl, "sow": 1, "plot": 2})
    with pytest.raises(A.ActionError, match="hold no plot"):
        A.act(k, c, "farm", {"camp": fl, "allow": b})
    assert A.act(k, a, "farm", {"camp": fl, "give": 2, "to": c}).startswith(f"Handed {fl} plot 2 to {c}")
    assert plot(k, fl, 2)["holder"] == c and plot(k, fl, 1)["holder"] == a
    assert any(e["type"] == "farm_set" and e["vis"] == "public" for e in k.events)
    api = k.api_for("_")
    farms = api["farms"](fl)
    assert farms[a]["plots"] == [1] and farms[c]["plots"] == [2] and api["plots"](fl)[0]["holder"] == a


def test_a_law_can_refuse_a_step_on_the_land():
    inst, k = world("society", ["subsistence.enabled=true", FIELDS, "law.v2=true"])
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    k.enact(k.new_law('title = "No Tending"\nintent = "x"\ndef before_tend(p, chain):\n    return False\n', "t"))
    a = SB.eaters(k)[0]
    fl = fields(k)
    set_food(k, a, 5)
    A.act(k, a, "farm", {"camp": fl, "sow": 1})
    with pytest.raises(A.ActionError, match="a law blocked tending"):
        A.act(k, a, "tend", {"camp": fl})


def test_an_institution_farm_is_worked_by_its_members_and_delivers_to_its_store(tmp_path):
    import yaml
    p = tmp_path / "w.yaml"
    p.write_text(yaml.safe_dump({"extends": ["nature_farming"], "contracts": {"enabled": True}, "start": {
        "institutions": [{"id": "A1", "name": "Co-op", "founder": "Gale", "members": ["Hob"], "charter": "a farmers' co-op"}],
        "stores": [{"id": "S1", "owner": "A1", "food": 0, "capacity": 4}],
        "farms": [{"owner": "A1", "plots": 2, "deliver": "S1", "crops": False, "works": {"irrigation": 1, "shed": 1}}]}}))
    inst = generator.generate(S.load(str(p)), 1)
    k = setup(inst, Kernel(inst))
    fl = fields(k)
    assert plot(k, fl, 1)["holder"] == "A1" and plot(k, fl, 1)["works"] == {"irrigation": 1}
    assert k.w["camps"][fl]["farms"]["A1"]["shed"] == 1
    set_food(k, "Hob", 10)
    A.act(k, "Hob", "farm", {"camp": fl, "sow": 3, "plot": 1})              # a member works it
    with pytest.raises(A.ActionError, match="A1's farm"):
        A.act(k, "Ivy", "tend", {"camp": fl, "plot": 1})
    ripen(k, fl, 1)
    A.act(k, "Hob", "farm", {"camp": fl, "reap": 1})
    y = 3 * (3.0 + 1.0)                                                   # irrigated
    from charter import accounts as AC
    assert SB.state(k)["stores"]["S1"]["holdings"]["food"] == pytest.approx(4)        # delivered up to the store's room
    assert k.bal(AC.treasury_of(k, "A1"), "food") == pytest.approx(y - 4, abs=1e-3)   # the rest to its treasury
    for x in ("Gale", "Hob"):                                             # no offices: its members manage and work it
        assert any(y.startswith(f"A1's farm at {fl} (you manage it and may work it") and "100% goes to A1 (store S1)" in y
                   and "plot 1" in y for y in SB.state_lines(k, x))
    assert not any("A1's farm" in y for y in SB.state_lines(k, "Ivy"))
    A.act(k, "Gale", "farm", {"camp": fl, "allow": "Ivy", "as": "A1"})    # its officer-less founder member manages it
    assert FL.may_work(k, "Ivy", k.w["camps"][fl], plot(k, fl, 2)) is None


def test_a_dead_holders_farm_passes_on():
    inst, k = small()
    fl = fields(k)
    a = SB.eaters(k)[0]
    FL.establish(k, a, fl, 2, crops=False)
    SB.on_death(k, a)
    assert plot(k, fl, 1)["holder"] != a
    assert any(e["type"] == "farm_set" and e["data"]["holder"] == a for e in k.events)


# ---------------------------------------------------------------------- tending: diminishing returns
def test_tending_has_diminishing_returns_once_per_round():
    inst, k = small()
    fl = fields(k)
    a = SB.eaters(k)[0]
    FL.establish(k, a, fl, 4, crops=False)
    set_food(k, a, 20)
    yields = {}
    for n, pid in enumerate((1, 2, 3)):
        A.act(k, a, "farm", {"camp": fl, "sow": 3, "plot": pid})
        for i in range(n + 1):
            if i == 2:
                with pytest.raises(A.ActionError, match="more tending adds nothing"):
                    A.act(k, a, "tend", {"camp": fl, "plot": pid})
                continue
            A.act(k, a, "tend", {"camp": fl, "plot": pid})
            with pytest.raises(A.ActionError, match="once per round"):
                A.act(k, a, "tend", {"camp": fl, "plot": pid})
            plot(k, fl, pid)["tended"] = None                               # (the next round)
    A.act(k, a, "farm", {"camp": fl, "sow": 3, "plot": 4})
    for pid in (1, 2, 3, 4):
        ripen(k, fl, pid)
        yields[pid] = FL.expected_yield(k, k.w["camps"][fl], plot(k, fl, pid), a)
    assert yields[4] == pytest.approx(9.0) and yields[1] == pytest.approx(9 * 1.15) and yields[2] == pytest.approx(9 * 1.22)
    assert plot(k, fl, 2)["tends"] == 2
    pl = plot(k, fl, 3)
    assert pl["tends"] == 2                                               # the third was refused: nothing more to gain
    f0 = pl["fertility"]
    A.act(k, a, "farm", {"camp": fl, "reap": 3})
    assert pl["fertility"] == pytest.approx(f0 - 0.10 * (1 - 0.25 * 2))  # tended twice: half the soil loss
    k.w["camps"][fl]["plots"][3]["fertility"] = 1.0
    A.act(k, a, "farm", {"camp": fl, "reap": 4})
    assert plot(k, fl, 4)["fertility"] == pytest.approx(0.9)


# ---------------------------------------------------------------------- improvements and their upkeep
def test_improvements_raise_their_dials_and_cost_materials():
    inst, k = small()
    fl = fields(k)
    a, b = SB.eaters(k)[:2]
    FL.establish(k, a, fl, 3, crops=False)
    for x in ("stone", "timber", "copper"):
        k.w["agents"][a]["holdings"].pop(x, None)
    with pytest.raises(A.ActionError, match="irrigation costs 4 timber, 6 stone"):
        A.act(k, a, "improve", {"kind": "irrigation", "camp": fl, "plot": 1})
    give(k, a, stone=30, timber=30, copper=5)
    with pytest.raises(A.ActionError, match="you hold no plot"):
        A.act(k, b, "improve", {"kind": "terraces", "camp": fl})
    A.act(k, a, "improve", {"kind": "irrigation", "camp": fl, "plot": 1})
    with pytest.raises(A.ActionError, match="at its most"):
        A.act(k, a, "improve", {"kind": "irrigation", "camp": fl, "plot": 1})
    A.act(k, a, "improve", {"kind": "terraces", "camp": fl, "plot": 2})
    A.act(k, a, "improve", {"kind": "terraces", "camp": fl, "plot": 2})
    A.act(k, a, "improve", {"kind": "shed", "camp": fl})
    A.act(k, a, "improve", {"kind": "plough"})
    assert k.bal(a, "stone") == pytest.approx(30 - 6 - 8 - 4) and k.bal(a, "timber") == pytest.approx(30 - 4 - 6 - 4)
    assert k.bal(a, "plough") == 1 and k.bal(a, "copper") == pytest.approx(2)
    c = k.w["camps"][fl]
    assert FL.plot_mult(k, c, plot(k, fl, 1)) == 4.0 and FL.seed_cap(k, c, plot(k, fl, 2)) == 5.0
    set_food(k, a, 20)
    with pytest.raises(A.ActionError, match="between 1 and 3"):
        A.act(k, a, "farm", {"camp": fl, "sow": 5, "plot": 1})
    A.act(k, a, "farm", {"camp": fl, "sow": 5, "plot": 2})
    assert plot(k, fl, 2)["seed"] == 5
    out = A.act(k, a, "farm", {"camp": fl, "sow": 3, "plots": [1, 3]})     # the plough: two plots, one action
    assert "plot 1" in out and "plot 3" in out
    with pytest.raises(A.ActionError, match="only with a plough"):
        A.act(k, b, "farm", {"camp": fl, "sow": 1, "plots": [5, 6]})
    assert any(e["type"] == "improvement" and e["vis"] == "public" and e["data"]["kind"] == "irrigation" for e in k.events)
    pl = ripen(k, fl, 2)                                                   # the shed slows rot
    end_round(k)
    assert pl["left"] == pytest.approx(1 - 0.5 * 0.4)                      # rot 0.5 x shed 0.4


def test_irrigation_halves_the_blight():
    def failed(irrigated):
        inst, k = small(["subsistence.fields.blight=0.5"])
        fl = fields(k)
        a = SB.eaters(k)[0]
        FL.establish(k, a, fl, 8, crops=True)
        if irrigated:
            for p in FL.farm_plots(k.w["camps"][fl], a):
                p["works"]["irrigation"] = 1
        for _ in range(3):
            end_round(k)
        return sum(1 for e in k.events if e["type"] == "crop_failed")
    assert failed(True) < failed(False)


def test_upkeep_is_paid_from_the_holder_or_the_work_decays():
    inst, k = small(["subsistence.fields.upkeep_every=2"])
    fl = fields(k)
    a = SB.eaters(k)[0]
    FL.establish(k, a, fl, 2, crops=False, works={"terraces": 2, "irrigation": 1, "shed": 1})
    for x in ("stone", "timber"):
        k.w["agents"][a]["holdings"].pop(x, None)
    give(k, a, stone=3, timber=0)
    assert any(x.startswith("Upkeep of your farm works: 6 stone, 1 timber due at the end of round 2") and "SHORT of stone, timber" in x
               for x in SB.state_lines(k, a))                             # 2 plots x (terraces 2 + irrigation 1) stone; the shed
    end_round(k)                                                           # round 1: nothing due
    assert not [e for e in k.events if e["type"] == "farm_upkeep"]
    end_round(k)                                                           # end of round 2: due
    ups = [e["data"] for e in k.events if e["type"] == "farm_upkeep"]
    assert ups and all(e["vis"] == [a] for e in k.events if e["type"] == "farm_upkeep")
    paid = [u for u in ups if u["paid"]]
    lost = [u for u in ups if not u["paid"]]
    assert sum(sum(u["bill"].values()) for u in paid) <= 3 and lost
    assert k.bal(a, "stone") == pytest.approx(3 - sum(u["bill"].get("stone", 0) for u in paid))
    assert k.w["camps"][fl]["farms"][a]["shed"] == 0                       # no timber: the shed decayed
    assert any(u["kind"] == "shed" and not u["paid"] for u in lost)


# ---------------------------------------------------------------------- skills
def test_rotation_and_seed_selection_are_learnt_and_taught():
    inst, k = small()
    fl = fields(k)
    a, b = SB.eaters(k)[:2]
    FL.establish(k, a, fl, 2, crops=False)
    with pytest.raises(A.ActionError, match="reap a crop first"):
        A.act(k, a, "practice", {"learn": "rotation"})
    set_food(k, a, 10)
    A.act(k, a, "farm", {"camp": fl, "sow": 3, "plot": 1})
    ripen(k, fl, 1)
    A.act(k, a, "farm", {"camp": fl, "reap": 1})
    with pytest.raises(A.ActionError, match="needs rotation first"):
        A.act(k, a, "practice", {"learn": "seed_selection"})
    assert A.act(k, a, "practice", {"learn": "rotation"}) == "Practised rotation: 1/3."
    A.act(k, a, "practice", {"learn": "rotation"})
    assert "now know rotation" in A.act(k, a, "practice", {"learn": "rotation"})
    assert any("skills: rotation" in x for x in SB.state_lines(k, a))
    plot(k, fl, 1)["fertility"] = 1.0
    A.act(k, a, "farm", {"camp": fl, "sow": 3, "plot": 1})
    ripen(k, fl, 1)
    A.act(k, a, "farm", {"camp": fl, "reap": 1})
    assert plot(k, fl, 1)["fertility"] == 1.0                              # rotation: the soil does not tire
    A.act(k, a, "practice", {"teach": "rotation", "to": b})
    assert "now knows rotation" in A.act(k, a, "practice", {"teach": "rotation", "to": b})   # 2 + 2 >= 3
    for _ in range(4):
        out = A.act(k, a, "practice", {"learn": "seed_selection"})
    assert "ripen a round sooner" in out
    A.act(k, a, "farm", {"camp": fl, "sow": 2, "plot": 2})
    assert plot(k, fl, 2)["ripe"] == k.r + 2
    assert any(e["type"] == "skill" and e["data"]["learnt"] for e in k.events)


# ---------------------------------------------------------------------- clearing: forest -> field
def test_clearing_makes_a_plot_held_by_the_clearer_and_shrinks_the_forest():
    inst, k = small()
    fo = SB.forest_camps(k)[0]
    c = k.w["camps"][fo]
    fl = c["fn"]["pair"]
    a = SB.eaters(k)[0]
    K0, Kg0, n0 = c["K"], c["game"]["K"], len(k.w["camps"][fl]["plots"])
    t0 = k.bal(a, "timber")
    for i in range(3):
        assert f"{i + 1}/4 work" in A.act(k, a, "clear", {"camp": fo})
        SB.state(k)["forage"] = {}                                        # (a new round's forest-action budget)
    assert c["K"] == K0 and any("clearing at" in x for x in SB.state_lines(k, a))
    out = A.act(k, a, "clear", {"camp": fo})
    assert out.startswith(f"Cleared a new plot at {fl}")
    assert len(k.w["camps"][fl]["plots"]) == n0 + 1 and k.w["camps"][fl]["plots"][-1]["holder"] == a
    assert c["K"] == pytest.approx(K0 - 16) and c["game"]["K"] == pytest.approx(Kg0 - 16) and c["S"] <= c["K"]
    assert k.bal(a, "timber") - t0 == pytest.approx(4 * 2.0)
    assert any(e["type"] == "plot_cleared" and e["vis"] == "public" for e in k.events)
    SB.state(k)["forage"] = {}
    c["K"] = c["fn"]["K0"] * 0.5 + 10                                      # near the floor
    with pytest.raises(A.ActionError, match="cleared as far as it can be"):
        A.act(k, a, "clear", {"camp": fo})


def test_a_field_yields_less_than_the_same_forest_area_kept_well():
    """The calibration rule (user, 15 Oct): the plants and game a cleared plot costs regrow, at their best (the logistic MSY, r K / 4,
    a season-averaged r; game's inflow ignored), more food a round than the plot yields net of seed when farmed well without capital
    (full seed, tended twice; fallow one round in four, cropped at the fertility floor, or cropped with rotation: the best of these);
    capital on the land (irrigation) makes it pay, and so does a mismanaged commons or the value of land of one's own."""
    c = SB.cfg({"subsistence": {"fields": {"enabled": True}}})
    fi, cl = c["fields"], c["fields"]["clear"]
    sea = c["seasons"]
    r_plants = c["forest"]["regrowth"] * (sea["p_lean"] * sea["lean"] + sea["p_plenty"] * sea["plenty"]
                                          + (1 - sea["p_lean"] - sea["p_plenty"]))
    msy = r_plants * cl["plants"] / 4 + c["game"]["regrowth"] * cl["game"] / 4
    tended = 1 + sum(fi["tend"]["bonus"])
    seed, g = fi["seed_max"], fi["grow"]
    best = max((seed * fi["mult"] * fert * tended - seed) / cycle
               for fert, cycle in ((1.0, g + 1), (fi["fertility_floor"], g), (1.0, g)))   # the last: rotation
    irrigated = (seed * (fi["mult"] + fi["improvements"]["irrigation"]["mult"]) * tended - seed) / g
    assert best < msy < irrigated
    assert best == pytest.approx(2.66, abs=0.01) and msy == pytest.approx(3.14, abs=0.01) and irrigated == pytest.approx(3.88, abs=0.01)


# ---------------------------------------------------------------------- shocks on the fields
def test_a_scheduled_shock_takes_standing_crops_and_blights_the_spell():
    sh = "subsistence.shocks=[{round: 1, plants: 1.0, crops: 0.0, blight: 1.0, season: lean, rounds: 2}]"
    inst, k = small([sh])
    fl = fields(k)
    a = SB.eaters(k)[0]
    FL.establish(k, a, fl, 4, crops=True)
    end_round(k)                                                           # the strike (end of round 1): every standing crop fails
    assert all(p["status"] == "fallow" for p in FL.farm_plots(k.w["camps"][fl], a))
    ev = next(e for e in k.events if e["type"] == "forest_shock")
    assert "standing crops have failed" in ev["data"]["text"] and ev["data"]["crops_lost"][fl] == 4
    set_food(k, a, 10)
    A.act(k, a, "farm", {"camp": fl, "sow": 1, "plot": 1})
    plot(k, fl, 1)["ripe"] = k.r + 1
    end_round(k)                                                           # a crop ripening in the spell: blight 1.0
    assert plot(k, fl, 1)["status"] == "fallow"


# ---------------------------------------------------------------------- the hunt: individual draws
def test_individual_expected_catch_grows_with_the_party_with_diminishing_returns():
    gp = SB.cfg({})["game"]
    assert gp["hunt_mode"] == "individual"
    tot = {E: FO.expected_catch(gp, E) for E in (1, 2, 3, 4, 6, 8, 12, 16)}
    per = {E: t / E for E, t in tot.items()}
    assert per[1] == pytest.approx(1.07, abs=0.02) and per[6] == pytest.approx(2.27, abs=0.02)
    es = sorted(tot)
    assert all(tot[x] < tot[y] for x, y in zip(es, es[1:]))               # the total grows with the party...
    marg = [(tot[y] - tot[x]) / (y - x) for x, y in zip(es, es[1:])]
    assert marg[-1] < marg[-2] < marg[-3] < marg[-4]                      # ... each extra hunter adding less
    pl1, pm1, _ = FO.unit_chances(gp, 1, 1.0)
    pl6, pm6, _ = FO.unit_chances(gp, 6, 1.0)
    assert pl6 > 5 * pl1 and pm6 > pm1                                     # a bigger party: each hunter's chance of bigger game
    shared = {**gp, "hunt_mode": "shared"}
    assert FO.expected_catch(shared, 12) < tot[12]                         # one quarry per party no longer caps a big party


def _hunt_total(n, mode, rounds=10):
    out = []
    for seed in range(1, 9):
        inst, k = world(extra=("agents={worker: 14, scientist: 0, legislator: 0, media: 0, board: 0, fixer: 0}", "subsistence.spoil=0", "subsistence.ration=0", "subsistence.seasons.enabled=false",
                               f"subsistence.game.hunt_mode={mode}", "subsistence.game.regrowth=5", "subsistence.game.inflow=1"),
                        seed=seed, rounds=rounds + 2)
        fo = SB.forest_camps(k)[0]
        for _ in range(rounds):
            hunters = [x for x in SB.eaters(k) if k.w["agents"][x].get("departed") is None][:n]   # (world events: departures)
            assert len(hunters) == n
            k.w["camps"][fo]["game"]["G"] = k.w["camps"][fo]["game"]["K"]   # full stock each round: the party size alone
            f0 = sum(k.bal(x, "food") for x in hunters)
            for x in hunters:
                A.act(k, x, "hunt", {"camp": fo, "party": "p"})
            end_round(k)
            out.append(sum(k.bal(x, "food") for x in hunters) - f0)
    return sum(out) / len(out)


def test_individual_hunting_totals_rise_with_party_size():
    t = {n: _hunt_total(n, "individual") for n in (1, 2, 4, 6, 8)}
    assert t[1] < t[2] < t[4] < t[6] < t[8]
    assert (t[8] - t[6]) / 2 < (t[6] - t[4]) / 2 + 1.0                     # diminishing (with sampling slack)


def test_each_hunter_keeps_its_own_catch_and_the_party_learns_the_total():
    inst, k = world(extra=(SMALL, "subsistence.spoil=0", "subsistence.ration=0"))
    fo = SB.forest_camps(k)[0]
    hs = SB.eaters(k)[:5]
    for _ in range(6):
        f0 = {x: k.bal(x, "food") for x in hs}
        for x in hs:
            A.act(k, x, "hunt", {"camp": fo, "party": "red"})
        end_round(k)
        res = {e["agent"]: e["data"] for e in k.events if e["type"] == "hunt_result" and e["round"] == k.r - 1}
        assert set(res) == set(hs) and len({r["catch"] for r in res.values()}) == 1
        for x in hs:
            assert k.bal(x, "food") - f0[x] == pytest.approx(res[x]["share"], abs=1e-3)
            assert res[x]["mode"] == "individual"
        assert sum(r["share"] for r in res.values()) == pytest.approx(res[hs[0]]["catch"], abs=1e-3)
        rec = [e for e in k.events if e["type"] == "hunt_round"][-1]
        assert rec["vis"] == "monitor" and rec["data"]["parties"][0]["kind"] == "individual"


def test_a_forest_made_before_engine_14_hunts_shared():
    inst, k = world(extra=(SMALL,))
    fo = SB.forest_camps(k)[0]
    gp = k.w["camps"][fo]["fn"]["game"]
    gp.pop("hunt_mode")
    assert FO.mode(gp) == "shared"


# ---------------------------------------------------------------------- dry runs: the scripted bot farms
@pytest.mark.slow
def test_the_scripted_bots_farm_in_a_dry_run(tmp_path):
    from charter import agents as AG
    from charter import runner
    sp = S.apply_overrides(S.load("nature_farming"), ["rounds=8", "shared_archive.enabled=false", "conflict.enabled=false"])
    inst = generator.generate(sp, 2)
    out = runner.run(inst, AG.ScriptedPolicy(2), tmp_path / "run", log=lambda *a: None)
    ev = [json.loads(x) for x in (out / "events.jsonl").read_text().splitlines() if x.strip()]
    kinds = {e["type"] for e in ev}
    assert {"farm_held", "sow", "tend", "reap", "hunt_result"} <= kinds
    net = sum(e["data"]["qty"] for e in ev if e["type"] == "reap") - sum(e["data"]["qty"] for e in ev if e["type"] == "sow")
    net += sum(e["data"]["share"] for e in ev if e["type"] == "hunt_result")
    net += sum(e["data"]["yield"] - e["data"].get("deducted", 0) for e in ev
               if e["type"] == "harvest" and e["data"].get("type") == "forest" and not e["data"].get("fell"))
    demand = sum(sum(e["data"]["stages"].values()) for e in ev if e["type"] == "subsistence_round")
    assert net >= 1.25 * demand                                           # §11a: normal output covers demand with headroom


def test_a_plough_covers_two_plots_and_may_break():
    inst, k = small(["subsistence.fields.improvements.plough.break=1"])
    fl = fields(k)
    a = SB.eaters(k)[0]
    FL.establish(k, a, fl, 3, crops=False)
    give(k, a, copper=3, timber=4)
    A.act(k, a, "improve", {"kind": "plough"})
    set_food(k, a, 10)
    out = A.act(k, a, "farm", {"camp": fl, "sow": 2, "plots": [1, 2]})
    assert "Your plough broke." in out and k.bal(a, "plough") == 0
    assert plot(k, fl, 1)["status"] == plot(k, fl, 2)["status"] == "growing"
    with pytest.raises(A.ActionError, match="only with a plough"):
        A.act(k, a, "tend", {"camp": fl, "plots": [1, 2]})
    assert any(e["type"] == "farm_upkeep" and e["data"]["kind"] == "plough" for e in k.events)


# ---------------------------------------------------------------------- earlier engines replay identically
ENGINE_13 = {"subsistence_small": ("dac0cc40fef4502a", "7c0ade6d2bd513e5"),     # events.jsonl, snapshots.json at engine 13
             "pairs_small": ("4afb3d910edee40f", "dc50fb91bf23adb8")}         # (tests/fixtures/charter_golden.json before 14)


def test_engine_14_flips_set_back_for_earlier_runs():
    from charter import provenance as PV
    from charter import settings as ST
    flips = {tuple(f[1]): (f[2], f[3]) for f in PV.ENGINE_FLIPS[14]["flips"]}
    assert flips[("game", "hunt_mode")] == ("shared", "individual") and flips[("forest", "clearing")] == (5, 0)
    with ST.use({"engine_version": 13, "defaults": {}}):
        c = SB.cfg({})
        assert c["game"]["hunt_mode"] == "shared" and c["forest"]["clearing"] == 5
        assert (c["fields"]["mult"], c["fields"]["plots_per_agent"], c["fields"]["plots_max_per_agent"]) == (3.5, 0.4, 0.8)
        assert c["fields"]["enabled"] is False
    assert SB.cfg({})["game"]["hunt_mode"] == "individual"


@pytest.mark.parametrize("name", sorted(ENGINE_13))
def test_runs_of_engine_13_replay_identically(name, tmp_path):
    """A subsistence golden case generated and played under engine 13's settings (the flips of 14 set back) is byte-identical to its
    engine 13 run: the same events and snapshots."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    import charter_golden_cases as GC
    import test_charter_golden as TG
    from charter import agents as AG
    from charter import runner
    from charter import settings as ST
    from charter import laweffects as LE                                # laws that work or fail loudly: off as before (until the
    from charter import schema as SC                                     # merge lists them in provenance.ENGINE_FLIPS)
    saved = {x: SC.EXTRA[x] for x in LE.BEFORE}
    SC.EXTRA.update(LE.BEFORE)
    try:
        _engine_13_run(name, tmp_path)
    finally:
        SC.EXTRA.update(saved)


def _engine_13_run(name, tmp_path):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    import charter_golden_cases as GC
    import test_charter_golden as TG
    from charter import agents as AG
    from charter import runner
    from charter import settings as ST
    with ST.use({"engine_version": 13, "defaults": {}}):
        inst = GC.instance(name)
    inst["settings"] = {"engine_version": 13, "defaults": {}}             # the run plays under them (runner.run: frozen_run)
    out = runner.run(inst, AG.ScriptedPolicy(GC.CASES[name][1]), tmp_path / name, log=lambda *a: None)
    fp = TG.files_fingerprint(out)
    assert (fp["events.jsonl"], fp["snapshots.json"]) == ENGINE_13[name]
