"""Established starting worlds (docs/review/27 §0, §6, §7): the three bugs, agents.names, the start block, the Offices Act, per-office
control of institution resources, and the Millbrook preset."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from charter import generator as GN
from charter import schema as SC
from charter import spec as S


def nature_child(tmp_path, body: dict) -> dict:
    p = tmp_path / "child.yaml"
    p.write_text(yaml.safe_dump({"extends": ["nature_subsistence"], **body}))
    return S.load(str(p))


# ---------------------------------------------------------------------- bug 1: food templates in a regime
def test_food_templates_pass_the_schema_in_a_regime_and_start_laws():
    sp = S.load("nature_subsistence")
    sp["regime"] = {"base": None, "name": "village", "constitution": "assembly",
                    "laws": [{"template": "Relief Act", "params": {"STORE": "S1", "BUDGET": 4}},
                             {"template": "Food Levy", "params": {"STORE": "S1"}}]}
    assert not [e for e in SC.validate(sp) if "regime" in e]
    sp["regime"]["laws"][0]["params"]["NOPE"] = 1
    assert any("Relief Act has no constant NOPE" in e for e in SC.validate(sp))
    sp2 = S.load("nature_subsistence")
    sp2["start_laws"] = ["Relief Act"]
    assert not [e for e in SC.validate(sp2) if "start_laws" in e]


def test_food_template_regime_law_is_enacted(tmp_path):
    sp = nature_child(tmp_path, {"regime": {"base": None, "name": "village", "constitution": "assembly",
                                            "laws": [{"template": "Relief Act", "params": {"BUDGET": 4}}]},
                                 "jurisdictions": {"start": "j0"}})
    inst = GN.generate(sp, 1)
    names = [s["name"] for s in inst["regime"]["statutes"]]
    assert "Relief Act" in names and "BUDGET = 4" in next(s["code"] for s in inst["regime"]["statutes"] if s["name"] == "Relief Act")


# ---------------------------------------------------------------------- bug 2: an inline regime is set whole
def test_child_inline_regime_replaces_the_inherited_one(tmp_path):
    sp = nature_child(tmp_path, {"regime": {"name": "village", "constitution": "assembly"}})
    assert sp["regime"] == {"name": "village", "constitution": "assembly"}        # no inherited base: state_of_nature
    sp = nature_child(tmp_path, {"regime": {"laws": [{"template": "Relief Act"}]}})
    assert any("needs a constitution" in e for e in SC.validate(sp))                # not silently voided: an error


def test_empty_mapping_clears_inherited_placements(tmp_path):
    sp = S.load("haiku100")
    assert sp["goals"]["explicit"] == {} and sp["models"]["overrides"] == {}


# ---------------------------------------------------------------------- bug 3: names fixed per seed; orphaned placements are errors
def small(names=None, **extra):
    sp = S.load("E0")
    sp["agents"] = {"worker": 3, "legislator": 2, "scientist": 0, "media": 0, "board": 0, "fixer": 0, **({"names": names} if names else {})}
    for k, v in extra.items():
        sp = S.set_path(sp, k, v)
    return sp


def test_names_fixed_are_seed_stable_and_bound_to_classes():
    sp = small({"worker": ["Wat", "Wynn", "Wren"], "legislator": ["Lyle", "Lark"]})
    for seed in (1, 2, 3):
        inst = GN.generate(copy.deepcopy(sp), seed)
        by = {a["id"]: a["cls"] for a in inst["agents"]}
        assert by == {"Wat": "worker", "Wynn": "worker", "Wren": "worker", "Lyle": "legislator", "Lark": "legislator"}
    inst = GN.generate(small("fixed"), 4)
    assert sorted(a["id"] for a in inst["agents"]) == sorted(GN.NAMES[:5])


def test_fixed_names_keep_every_other_draw():
    a = GN.generate(small(), 7)
    # the same world with the drawn names given explicitly, per class in roster order of first appearance
    names = {}
    for x in a["agents"]:
        names.setdefault(x["cls"], []).append(x["id"])
    b = GN.generate(small(names), 7)
    assert [x["cls"] for x in a["agents"]] == [x["cls"] for x in b["agents"]]
    assert [x["endowment"] for x in a["agents"]] == [x["endowment"] for x in b["agents"]]
    assert [x["rights"] for x in a["agents"]] == [x["rights"] for x in b["agents"]]


def test_grand35_names_are_seed_35s():
    sp = S.load("grand35")
    for seed in (1, 35):
        inst = GN.generate(copy.deepcopy(sp), seed)
        assert inst["agents"] and {a["id"]: a["goal"]["primary"] for a in inst["agents"]}["Clara"] == "Bloodline Eliminator"


def test_orphaned_placement_is_an_error():
    sp = small(**{"goals.explicit": {"Nobody": "Wealth"}})
    with pytest.raises(ValueError, match="match no agent.*goals.explicit: Nobody.*agents.names"):
        GN.generate(sp, 1)
    sp = small({"worker": ["Wat", "Wynn", "Wren"], "legislator": ["Lyle", "Lark"]}, **{"models.overrides": {"Wat": "x", "Ghost": "y"}})
    with pytest.raises(ValueError, match="models.overrides: Ghost"):
        GN.generate(sp, 1)


def test_bad_names():
    with pytest.raises(ValueError, match="2 names for 3 agents"):
        GN.generate(small({"worker": ["A", "B"], "legislator": ["C", "D"]}), 1)
    with pytest.raises(ValueError, match="distinct"):
        GN.generate(small(["A", "A", "B", "C", "D"]), 1)
    assert any("agents.names" in e for e in SC.validate(small(7)))


# ---------------------------------------------------------------------- the start block, offices, per-office control
NAMES6 = ["Ada", "Bo", "Cy", "Di", "Ed", "Fay"]


def village(rounds=3, **start_over):
    """A small established village: J0 with a council and a keeper of the granary S1, one house (A1) with a head who controls its
    treasury and store S2 and a clerk with a bounded pay power, wages, a penny with a levy, channels, camp rights, kin."""
    sp = S.load("charter/specs/survival/base.yaml")
    sp = S.deep_merge(sp, {
        "agents": {"worker": 6, "names": list(NAMES6)}, "rounds": rounds, "parallel_calls": 1,
        "institutions": {"unified": True, "grants": True, "succession": True, "office_control": True},
        "jurisdictions": {"enabled": False}, "contracts": {"scripted": False},
        "regime": {"base": None, "name": "v", "constitution": "assembly"},
        "goals": {"explicit": {"Ada": "Wealth"}},
    })
    sp["regime"] = {"base": None, "name": "v", "constitution": "assembly",
                    "laws": [{"template": "Simple Majority Procedure", "params": {"ELECTORATE": "J0.council",
                                                                                 "CLASSES": ["ordinary", "structural", "procedural"]}}]}
    start = {
        "rights": {n: ["vote", "propose"] for n in NAMES6[:5]},
        "currencies": [{"name": "penny", "issuer": "J0"}],
        "institutions": [
            {"id": "J0", "offices": {
                "council": {"title": "Councillor", "holders": ["Ada", "Bo"], "seats": 2, "term": 2, "term_calendar": True,
                            "powers": ["speak"], "duties": "Decide the laws.", "succession": {"rule": "election", "electorate": "vote"}},
                "keeper": {"title": "Keeper", "holders": ["Cy"], "controls": ["store:S1"], "duties": "Keep the granary.",
                           "succession": {"rule": "election", "electorate": "J0.council"}}},
             "treasury": {"penny": 50, "timber": 40}},
            {"id": "A1", "name": "House Ada", "founder": "Ada", "members": ["Di", "Ed"], "charter": "A house.",
             "offices": {"head": {"title": "Head", "holders": ["Ada"], "controls": ["treasury", "store:S2"], "powers": ["speak"],
                                  "duties": "Lead the house."},
                         "clerk": {"title": "Clerk", "holders": ["Di"], "powers": [{"action": "transfer", "item": "penny", "qty": 3}]}},
             "treasury": {"penny": 40}},
        ],
        "wages": [{"employer": "A1", "worker": "Ed", "item": "penny", "qty": 2}],
        "stores": [{"id": "S1", "owner": "J0", "food": 30, "capacity": 100, "name": "granary"},
                   {"id": "S2", "owner": "A1", "food": 10}],
        "holdings": {"Fay": {"penny": 5}},
        "kin": [{"parent": "Ada", "child": "Ed"}],
        "camp_rights": [{"resource": "copper", "members": "A1", "exclusive": True}],
        "channels": [{"id": "hall", "owner": "J0", "by": "Ada", "readers": {"office": "J0.council"}, "writers": {"office": "J0.council"}},
                     {"id": "@J0", "readers": {"office": "J0.council"}},
                     {"id": "news", "owner": "Fay", "readers": {"all": True}, "writers": {"agents": ["Fay"]}, "subscribers": ["Ada", "Bo"]}],
        "laws": [{"template": "Payment Levy", "params": {"ITEM": "penny", "RATE": 0.1}},
                 {"template": "Granary Ration", "params": {"STORE": "S1", "OFFICE": "J0.keeper", "CAP": 2}}],
    }
    start.update(start_over)
    sp["start"] = start
    return sp


def run_village(tmp_path, sp=None, seed=1):
    from charter import agents as AG
    from charter import runner
    inst = GN.generate(sp or village(), seed)
    out = runner.run(inst, AG.ScriptedPolicy(seed), tmp_path / "run", log=lambda *a: None)
    return inst, Path(out)


def kernel_after_setup(run):
    from charter import start as STT
    return STT._kernel_at(run, 0)[1]


def test_start_compiles_into_round0_interventions_recorded_like_any(tmp_path):
    import json
    inst, run = run_village(tmp_path)
    sched = inst["start"]["schedule"]
    assert sched and all(e["op"] == "establish" and e["at"] == {"round": 0, "phase": "setup"} for e in sched)
    recs = [json.loads(x) for x in (run / "interventions.jsonl").read_text().splitlines()]
    assert [r["id"] for r in recs][:len(sched)] == [e["id"] for e in sched]
    assert not [r for r in recs if "error" in r], [r for r in recs if "error" in r]
    assert "establish" in (run / "interventions.yaml").read_text()
    k = kernel_after_setup(run)
    from charter import accounts as AC
    from charter import institutions as IN
    from charter import subsistence as SB
    assert IN.holders(k, "J0", "council") == ["Ada", "Bo"] and IN.holders(k, "J0", "keeper") == ["Cy"]
    assert IN.holders(k, "A1", "head") == ["Ada"] and IN.holders(k, "A1", "clerk") == ["Di"]
    assert IN.members(k, "A1") == ["Ada", "Di", "Ed"]
    assert k.bal(AC.treasury_of(k, "A1"), "penny") == 40 and k.bal("reserve", "timber") == 40
    st = SB.state(k)["stores"]
    assert st["S1"]["owner"] == "J0" and st["S1"]["holdings"]["food"] == 30 and st["S1"]["capacity"] == 100
    assert k.bal("Fay", "penny") == 5 and "vote" in k.w["agents"]["Bo"]["rights"] and "vote" not in k.w["agents"]["Fay"]["rights"]
    assert k.w["life"]["parent"]["Ed"] == "Ada"
    copper = [c for c in inst["camps"] if c.get("resource") == "copper" and not c.get("open")]
    for c in copper:
        assert sorted(a for a, v in k.w["agents"].items() if f"harvest:{c['id']}" in v["rights"]) == ["Ada", "Di", "Ed"]
    assert k.w["channels"]["@J0"]["readers"] == {"office": "J0.council"}
    assert sorted(k.w["channels"]["news"]["subscribers"]) == ["Ada", "Bo"]
    assert [l["title"] for l in k.active_laws()][-2:] == ["Payment Levy", "Granary Ration"]
    assert inst["repairs"] == []                                   # start grants propose and vote: no repair hands them out


def test_lived_checks_pass_on_the_village(tmp_path):
    from charter import start as STT
    _, run = run_village(tmp_path)
    rows = STT.lived(run)
    bad = [r for r in rows if not r["ok"] and not r["check"].startswith(("elections", "food"))]
    assert not bad, bad
    names = {r["check"] for r in rows}
    assert {"office J0.keeper", "store S1 (J0)", "channel hall", "office A1.clerk"} <= names


def test_unresolved_start_names_are_errors():
    for over, msg in [({"holdings": {"Ghost": {"penny": 1}}}, "start.holdings: Ghost"),
                      ({"stores": [{"id": "S2", "owner": "J0"}]}, "S1, S2"),
                      ({"wages": [{"employer": "A9", "worker": "Ed", "qty": 1}]}, "start.wages.employer: A9"),
                      ({"camp_rights": [{"resource": "unobtainium", "holders": ["Ada"]}]}, "no camp")]:
        with pytest.raises(ValueError, match=msg):
            GN.generate(village(**over), 1)


def test_start_shape_is_checked_by_the_schema():
    sp = village()
    sp["start"]["nope"] = 1
    sp["start"]["institutions"][1]["admission"] = "maybe"
    errs = SC.validate(sp)
    assert any("start.nope: unknown section" in e for e in errs) and any("admission" in e for e in errs)


def test_only_the_keeper_draws_from_the_granary_and_officers_pay_by_office(tmp_path):
    from charter import actions as A
    from charter import subsistence as SB
    from charter.actions import ActionError
    _, run = run_village(tmp_path)
    k = kernel_after_setup(run)
    assert [a for a in k.players() if SB.can_withdraw(k, a, SB.state(k)["stores"]["S1"])] == ["Cy"]
    with pytest.raises(ActionError, match="(?i)keeper"):
        A.act(k, "Ada", "withdraw", {"store": "S1", "qty": 1})                          # a councillor (an officer of J0) may not
    A.act(k, "Cy", "withdraw", {"store": "S1", "qty": 2})
    with pytest.raises(ActionError, match="at most 2 food a round"):
        A.act(k, "Cy", "withdraw", {"store": "S1", "qty": 1})                           # the Granary Ration's cap
    with pytest.raises(ActionError):
        A.act(k, "Di", "withdraw", {"store": "S2", "qty": 1})                           # the house store: its head's
    A.act(k, "Ada", "withdraw", {"store": "S2", "qty": 1})
    from charter import accounts as AC
    before, tr = k.bal("Fay", "penny"), k.bal(AC.treasury_of(k, "A1"), "penny")
    A.act(k, "Ada", "transfer", {"to": "Fay", "item": "penny", "qty": 10, "as": "A1"})   # the head controls the treasury
    assert round(k.bal("Fay", "penny") - before, 6) == 10.0
    assert round(tr - k.bal(AC.treasury_of(k, "A1"), "penny"), 6) == 11.0   # the 10% Payment Levy, charged to the payer
    A.act(k, "Di", "transfer", {"to": "Fay", "item": "penny", "qty": 3, "as": "A1"})     # the clerk's bounded power
    with pytest.raises(ActionError, match="none of your offices"):
        A.act(k, "Di", "transfer", {"to": "Fay", "item": "penny", "qty": 1, "as": "A1"})  # over its bound this round
    with pytest.raises(ActionError):
        A.act(k, "Ed", "transfer", {"to": "Fay", "item": "penny", "qty": 1, "as": "A1"})  # a plain member


def test_office_state_lines_show_duties_and_control(tmp_path):
    from charter import agents as AG
    _, run = run_village(tmp_path)
    k = kernel_after_setup(run)
    v = AG.state_view(k, "Cy")
    assert "Your office: Keeper of J0" in v and "Keep the granary." in v and "store S1 (withdraw)" in v
    assert "voters: holders of J0.council" in v
    assert "Your office:" not in AG.state_view(k, "Fay")


def test_office_control_off_keeps_the_residual():
    from charter import institutions as IN
    from charter import subsistence as SB
    from charter.kernel import Kernel
    sp = village()
    sp["institutions"]["office_control"] = False
    inst = GN.generate(sp, 1)
    k = Kernel(inst)
    k.w.setdefault("offices", {})["J0"] = {"keeper": {"id": "J0.keeper", "office": "keeper", "title": "K", "powers": [], "grants": [],
                                                      "seats": None, "term": None, "law": "L1", "declared": 0, "past": [],
                                                      "holders": [{"holder": "Cy", "since": 0, "term_end": None}],
                                                      "controls": ["store:S1"]},
                                           "other": {"id": "J0.other", "office": "other", "title": "O", "powers": [], "grants": [],
                                                     "seats": None, "term": None, "law": "L1", "declared": 0, "past": [],
                                                     "holders": [{"holder": "Bo", "since": 0, "term_end": None}]}}
    s = {"id": "S1", "owner": "J0"}
    assert SB.can_withdraw(k, "Bo", s) and SB.can_withdraw(k, "Cy", s)   # off: any officer (the old residual)
    assert IN.office_lines(k, "Cy") == []


def test_term_calendar_and_electorate(tmp_path):
    import json
    _, run = run_village(tmp_path, village(rounds=5))
    ev = [json.loads(x) for x in (run / "events.jsonl").read_text().splitlines()]
    vac = sorted({e["round"] for e in ev if e["type"] == "office_vacant" and e["data"]["cause"] == "term"})
    assert vac and vac[0] == 1                                      # term 2 on the calendar: ends after round 2 (index 1)
    ballots = [e["data"] for e in ev if e["type"] == "ballot_open" and e["data"]["question"].startswith("Elect the Councillor")]
    assert ballots and all("Fay" not in b["electorate"] for b in ballots)   # electorate: holders of vote only


def test_offices_act_and_new_templates_are_library_law():
    from charter import institutions as IN
    from charter import library as LB
    code = LB.instantiate("Offices Act", {"offices": {"keeper": {"title": "Keeper", "duties": "Keep it.", "controls": ["store:S1"],
                                                                 "term": 4, "term_calendar": True,
                                                                 "succession": {"rule": "election", "electorate": "J0.council"}}}})
    d = IN.parse_offices(code, True)["keeper"]
    assert d["duties"] == "Keep it." and d["controls"] == ["store:S1"] and d["calendar"] and d["succession"]["electorate"] == "J0.council"
    for name in ("Offices Act", "Granary Ration", "Payment Levy", "Wage Roll"):
        assert name in LB.ESTABLISHED and LB.info2(name)["params"] is not None
    from charter import lawlang as L
    with pytest.raises(L.LawError, match="controls"):
        IN.parse_offices(LB.instantiate("Offices Act", {"offices": {"x": {"controls": ["the moon"]}}}))
    assert LB.established_templates(S.load("nature_subsistence")) == []      # listed only with institutions.office_control


def test_scheduled_shock_and_forced_season():
    from charter import subsistence as SB
    c = SB._cfg({"shocks": [{"round": 3, "plants": 0.5, "season": "lean", "rounds": 2}]})
    assert [SB.forced_season(c, r) for r in range(2, 7)] == [None, "lean", "lean", None, None]
    sp = S.load("nature_subsistence")
    sp["subsistence"]["shocks"] = [{"round": 0}]
    assert any("subsistence.shocks[0]" in e for e in SC.validate(sp))


def test_millbrook_preset_checks_and_generates():
    sp = S.load("millbrook")
    assert SC.validate(sp) == []
    for seed in (1, 2):
        inst = GN.generate(copy.deepcopy(sp), seed)
        models = {a["id"]: a["model"] for a in inst["agents"]}
        assert sum(m == "claude-opus-5-5" for m in models.values()) == 10 and len(models) == 21
        assert inst["start"]["schedule"] and inst["repairs"] == []
